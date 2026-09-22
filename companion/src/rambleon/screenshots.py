"""Pair WoW screenshot files with a session by time. References only; nothing is copied unless asked."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

SCREENSHOT_RE = re.compile(r"^WoWScrnShot_(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.(jpg|jpeg|png|tga)$", re.IGNORECASE)
WINDOW = 60  # seconds of slack around the session


def screenshot_time(path: Path) -> int:
    """The file's mtime is authoritative; the filename only breaks ties."""
    try:
        return int(path.stat().st_mtime)
    except OSError:
        m = SCREENSHOT_RE.match(path.name)
        if m:
            mm, dd, yy, hh, mi, ss = (int(x) for x in m.groups()[:6])
            return int(datetime(2000 + yy, mm, dd, hh, mi, ss).timestamp())
        return 0


def find_screenshots(directory: Path | None, start: int | None, end: int | None) -> list[dict[str, Any]]:
    if not directory or not directory.is_dir() or not start:
        return []
    end = end or start
    out = []
    for p in sorted(directory.iterdir()):
        if not p.is_file() or not SCREENSHOT_RE.match(p.name):
            continue
        taken = screenshot_time(p)
        if start - WINDOW <= taken <= end + WINDOW:
            out.append({"path": str(p), "file": p.name, "takenAt": taken})
    return out


def attach_screenshots(session: dict[str, Any], directory: Path | None, copy_to: Path | None = None) -> dict[str, Any]:
    shots = find_screenshots(directory, session.get("startedAt"), session.get("endedAt") or session.get("lastSeen"))
    events = session.get("events", [])
    for shot in shots:
        nearest, best = None, None
        for i, ev in enumerate(events):
            d = abs(ev["t"] - shot["takenAt"])
            if best is None or d < best:
                nearest, best = i, d
        shot["nearestEventIndex"] = nearest
        shot["nearestEventSeconds"] = best
        if copy_to is not None:
            dest_dir = copy_to / session["id"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / shot["file"]
            if not dest.exists():
                shutil.copy2(shot["path"], dest)
            shot["archived"] = str(dest)
    existing = {s.get("file") for s in session.get("screenshots", [])}
    merged = list(session.get("screenshots", []))
    for shot in shots:
        if shot["file"] not in existing:
            merged.append(shot)
    session["screenshots"] = merged
    return session
