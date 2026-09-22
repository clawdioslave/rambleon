"""Watch Rambleon's SavedVariables and archive every write. This is the defence against the
Forever beta bug: WoW may forget, the archive does not."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

from .archive import Archive, blake
from .luaparse import LuaParseError, TornFile, parse, to_python
from .normalize import sessions_from_db
from .paths import Paths
from .screenshots import attach_screenshots

Log = Callable[[str], None]
STABLE_POLLS = 2
RETRY_DELAYS = (0.5, 1.0, 2.0, 5.0)


def _signature(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _read(path: Path) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def process_file(path: Path, paths: Paths, archive: Archive, log: Log, copy_screenshots: bool = False,
                 allow_bak: bool = True) -> list[str]:
    """Snapshot, parse and archive one SavedVariables file. Returns a list of outcome strings."""
    data = _read(path)
    if data is None:
        return []
    h = blake(data)
    if archive.has_hash(h):
        return []
    parsed = None
    error: Exception | None = None
    for attempt, delay in enumerate((0.0,) + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
            fresh = _read(path)
            if fresh is None:
                return []
            if fresh != data:
                data = fresh
                h = blake(data)
                if archive.has_hash(h):
                    return []
        try:
            parsed = parse(data)
            error = None
            break
        except TornFile as e:
            error = e
            continue
        except LuaParseError as e:
            error = e
            break
    if parsed is None:
        failed = archive.store_failed(data, path, f"{type(error).__name__}: {error}")
        log(f"could not parse {paths.redact(path)}: {error} — preserved at {failed.name}")
        bak = path.with_name(path.name + ".bak")
        if allow_bak and bak.exists():
            log("trying the .bak copy WoW kept from the previous flush")
            return process_file(bak, paths, archive, log, copy_screenshots, allow_bak=False)
        return [f"failed {path.name}"]

    raw_path, h = archive.snapshot_raw(data, path)
    if raw_path is None:
        return []
    outcomes: list[str] = []
    db = parsed.get("RambleonDB")
    if db is None:
        log(f"{paths.redact(path)} has no RambleonDB table (nothing to archive)")
        return ["no-db"]
    sessions = sessions_from_db(to_python(db))
    if not sessions:
        log(f"{paths.redact(path)}: RambleonDB is empty — no sessions to archive (expected right after a fresh login)")
        return ["empty"]
    capture = {
        "capturedAt": int(time.time()),
        "rawSnapshot": str(raw_path.relative_to(archive.root)),
        "sourceHash": h,
        "sourceFile": paths.redact(path),
    }
    for s in sessions:
        attach_screenshots(s, paths.screenshots_dir, archive.screenshots_dir if copy_screenshots else None)
        outcome, out_path = archive.upsert_session(s, capture)
        c = s.get("counters", {})
        summary = f"{len(s.get('events', []))} events, {s.get('state')}"
        if outcome in ("new", "updated"):
            log(f"captured {s['id']} ({summary}) → {out_path.name if out_path else '?'} [{outcome}]")
        elif outcome == "rejected":
            log(f"kept existing archive for {s['id']} (incoming copy had fewer events)")
        outcomes.append(f"{outcome} {s['id']}")
    archive.rebuild_index()
    return outcomes


def ingest_once(paths: Paths, archive: Archive, log: Log, copy_screenshots: bool = False) -> list[str]:
    files = paths.saved_variables_files()
    if not files:
        log("no Rambleon SavedVariables files found yet (play a session and end the chapter first)")
        return []
    outcomes: list[str] = []
    for f in files:
        outcomes += process_file(f, paths, archive, log, copy_screenshots)
    return outcomes


def watch(paths: Paths, archive: Archive, log: Log, interval: float = 1.0, copy_screenshots: bool = False,
          stop_after: float | None = None, rescan: float = 5.0) -> None:
    archive.ensure()
    archive.pid_path.write_text(str(os.getpid()))
    tracked: dict[Path, dict[str, Any]] = {}
    last_glob = 0.0
    files: list[Path] = []
    started = time.time()
    log("watching for Rambleon SavedVariables writes (Ctrl-C to stop)")
    ingest_once(paths, archive, log, copy_screenshots)
    for f in paths.saved_variables_files():
        tracked[f] = {"sig": _signature(f), "stable": STABLE_POLLS, "done": _signature(f)}
    try:
        while True:
            now = time.time()
            if now - last_glob >= rescan:
                files = paths.saved_variables_files()
                last_glob = now
                for f in files:
                    tracked.setdefault(f, {"sig": None, "stable": 0, "done": None})
            for f, st in list(tracked.items()):
                sig = _signature(f)
                if sig is None:
                    st["sig"] = None
                    st["stable"] = 0
                    continue
                if sig != st["sig"]:
                    st["sig"] = sig
                    st["stable"] = 0
                    continue
                st["stable"] += 1
                if st["stable"] >= STABLE_POLLS and sig != st["done"]:
                    st["done"] = sig
                    process_file(f, paths, archive, log, copy_screenshots)
            if stop_after is not None and time.time() - started >= stop_after:
                return
            time.sleep(interval)
    finally:
        try:
            archive.pid_path.unlink()
        except OSError:
            pass
