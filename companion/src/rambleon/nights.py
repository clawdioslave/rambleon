"""A chapter is a night in Azeroth: every session a character played that evening, stitched together.
Sessions stay as they were archived; nights are derived on demand."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from .archive import Archive, load_json
from .config import load_local_config
from .model import COUNTER_KEYS, SUSPEND_TIMEOUT
from .screenshots import pair_screenshots

CUTOFF_HOUR = 5  # play that runs past midnight still belongs to the evening it started


def night_date(started_at: int | None) -> str:
    dt = datetime.fromtimestamp(started_at or 0)
    if dt.hour < CUTOFF_HOUR:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def chapter_splits() -> list[int]:
    """`[chapters] splits = ["2026-09-25T15:10"]` in rambleon.local.toml: a session that starts at or after one of
    these local times begins a new chapter that same day — for when the player closes a chapter and plays on."""
    cfg = load_local_config().get("chapters", {})
    raw = cfg.get("splits") or [] if isinstance(cfg, dict) else []
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(datetime.fromisoformat(str(item)).timestamp()))
        except ValueError:
            continue
    return sorted(out)


def night_part(started_at: int | None, splits: list[int] | None = None) -> int:
    """0 for the day's first chapter; n for the chapter after the n-th split that falls on the same night."""
    date = night_date(started_at)
    splits = chapter_splits() if splits is None else splits
    return sum(1 for t in splits if night_date(t) == date and (started_at or 0) >= t)


def _piece(session: dict[str, Any], events: list[dict[str, Any]], suffix: str, started: int, ended: int | None,
           last_seen: int | None, state: str | None) -> dict[str, Any]:
    """One slice of a session, as if it had been its own session. Event-derived counters are exact; kills, XP
    and loot are shared out by time, since the archive only holds their totals."""
    p = dict(session)
    p["id"] = f"{session['id']}{suffix}"
    p["events"] = events
    p["startedAt"], p["endedAt"], p["lastSeen"], p["state"] = started, ended, last_seen, state
    whole = max(1, (session.get("lastSeen") or session.get("endedAt") or started) - (session.get("startedAt") or started))
    frac = max(0.0, min(1.0, ((last_seen or ended or started) - started) / whole))
    c = dict(session.get("counters", {}))
    by_type = {}
    for e in events:
        by_type[e.get("type")] = by_type.get(e.get("type"), 0) + 1
    c.update({"deaths": by_type.get("DEATH", 0), "questsCompleted": by_type.get("QUEST_COMPLETED", 0),
              "questsAccepted": by_type.get("QUEST_ACCEPTED", 0), "levelsGained": by_type.get("LEVEL_UP", 0),
              "objectivesCompleted": by_type.get("OBJECTIVE_COMPLETE", 0), "screenshots": by_type.get("SCREENSHOT", 0),
              "notes": by_type.get("NOTE", 0), "marks": by_type.get("MARK", 0)})
    for k in ("kills", "xpGained", "loot", "achievements"):
        c[k] = round((session.get("counters", {}).get(k) or 0) * frac)
    p["counters"] = c
    p["playedSeconds"] = round((session.get("playedSeconds") or 0) * frac)
    lo, hi = started, (last_seen or ended or started)
    overlaps = lambda a, b: lo <= (b or 0) and (a or 0) <= hi
    p["zones"] = [dict(z) for z in session.get("zones", []) if overlaps(z.get("firstSeen"), z.get("lastSeen"))]
    p["people"] = [dict(q) for q in session.get("people", []) if overlaps(q.get("firstSeen"), q.get("lastSeen"))]
    p["kills"] = {n: dict(k) for n, k in (session.get("kills") or {}).items() if overlaps(k.get("firstAt"), k.get("lastAt"))}
    p["screenshots"] = [dict(sh) for sh in session.get("screenshots", []) if lo <= (sh.get("takenAt") or 0) <= hi]
    ch = dict(session.get("character", {}))
    levels = [e.get("level") for e in events if e.get("level")]
    if levels:
        ch["startLevel"], ch["endLevel"] = levels[0], levels[-1]
    p["character"] = ch
    return p


def split_session(session: dict[str, Any], splits: list[int]) -> list[dict[str, Any]]:
    """A chapter split that falls inside a session cuts it at the next RESUMED event (the player logged out and
    back in at the split) — or at the first event after the split if they never left. Pieces read like sessions."""
    started, seen = session.get("startedAt") or 0, session.get("lastSeen") or session.get("endedAt") or 0
    cuts = [t for t in splits if started < t <= seen and night_date(t) == night_date(started)]
    if not cuts:
        return [session]
    cut = cuts[0]
    events = sorted(session.get("events", []), key=lambda e: e.get("t") or 0)
    resumed = [e for e in events if e.get("type") == "RESUMED" and (e.get("t") or 0) >= cut]
    later = [e for e in events if (e.get("t") or 0) >= cut]
    if not later:
        return [session]
    cut_t = (resumed[0] if resumed else later[0]).get("t")
    before = [e for e in events if (e.get("t") or 0) < cut_t]
    after = [e for e in events if (e.get("t") or 0) >= cut_t]
    if not before or not after:
        return [session]
    n = session["id"].count("#") + 2
    first = _piece(session, before, "", started, before[-1].get("t"), before[-1].get("t"), "ended")
    second = _piece(session, after, f"#{n}", cut_t, session.get("endedAt"), session.get("lastSeen"), session.get("state"))
    return [first] + split_session(second, cuts[1:])


def _merge_keyed(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], key: str, sum_fields: tuple[str, ...]) -> None:
    index = {str(e.get(key)): e for e in existing}
    for item in incoming:
        k = str(item.get(key))
        if k in index:
            e = index[k]
            for f in sum_fields:
                e[f] = (e.get(f) or 0) + (item.get(f) or 0)
            e["lastSeen"] = max(e.get("lastSeen") or 0, item.get("lastSeen") or 0)
        else:
            copy = dict(item)
            existing.append(copy)
            index[k] = copy


def session_over(s: dict[str, Any], now: float | None = None) -> bool:
    """Judged now, not when the snapshot was normalized: ended, or not seen for longer than the resume window."""
    if s.get("state") == "ended":
        return True
    now = time.time() if now is None else now
    return (now - (s.get("lastSeen") or s.get("startedAt") or 0)) > SUSPEND_TIMEOUT


def build_night(sessions: list[dict[str, Any]], now: float | None = None, part: int = 0) -> dict[str, Any]:
    sessions = sorted(sessions, key=lambda s: s.get("startedAt") or 0)
    first, last = sessions[0], sessions[-1]
    date = night_date(first.get("startedAt"))
    if part:                      # a later chapter on the same night keeps its own id and file names
        date = f"{date}-{part + 1}"
    night: dict[str, Any] = {
        "kind": "night",
        "schemaVersion": first.get("schemaVersion"),
        "id": f"night-{date}-{first['character'].get('slug', 'unknown')}",
        "nightDate": date,
        "sessionIds": [s["id"] for s in sessions],
        "state": "ended" if all(session_over(s, now) for s in sessions) else "open",
        "startedAt": first.get("startedAt"),
        "endedAt": max((s.get("endedAt") or s.get("lastSeen") or 0) for s in sessions) or None,
        "playedSeconds": sum(s.get("playedSeconds") or 0 for s in sessions),
        "endReason": last.get("endReason"),
        "character": dict(last.get("character", {})),
        "client": dict(last.get("client", {})),
        "counters": {k: sum((s.get("counters", {}).get(k) or 0) for s in sessions) for k in COUNTER_KEYS},
        "events": [], "zones": [], "people": [], "kills": {}, "screenshots": [], "failedEvents": [],
    }
    night["character"]["startLevel"] = first.get("character", {}).get("startLevel")
    night["character"]["endLevel"] = last.get("character", {}).get("endLevel")
    for i, s in enumerate(sessions):
        for ev in s.get("events", []):
            t = ev.get("type")
            if t == "RESUMED":
                continue
            if t == "SESSION_START" and i > 0:
                continue
            if t == "SESSION_END" and i < len(sessions) - 1:
                continue
            night["events"].append(ev)
        _merge_keyed(night["zones"], [dict(z, _k=f"{z.get('zone')}|{z.get('subzone') or ''}") for z in s.get("zones", [])], "_k", ("visits",))
        _merge_keyed(night["people"], s.get("people", []), "name", ("seconds", "joins"))
        for name, info in (s.get("kills") or {}).items():
            k = night["kills"].setdefault(name, {"count": 0, "xp": 0, "firstAt": info.get("firstAt"), "lastAt": info.get("lastAt")})
            k["count"] += info.get("count") or 0
            k["xp"] += info.get("xp") or 0
            k["lastAt"] = max(k.get("lastAt") or 0, info.get("lastAt") or 0)
        seen = {sh.get("file") for sh in night["screenshots"]}
        night["screenshots"] += [sh for sh in s.get("screenshots", []) if sh.get("file") not in seen]
        for fe in s.get("failedEvents", []):
            if fe not in night["failedEvents"]:
                night["failedEvents"].append(fe)
    for z in night["zones"]:
        z.pop("_k", None)
    night["events"].sort(key=lambda e: e.get("t") or 0)
    # screenshot → its event again, over the merged timeline
    night["screenshots"] = [dict(sh) for sh in night["screenshots"]]
    pair_screenshots(night["screenshots"], night["events"])
    night["counters"]["zonesVisited"] = len(night["zones"])
    return night


def nights(archive: Archive, slug: str | None = None) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    splits = chapter_splits()
    for row in archive.list_sessions():
        if row.get("trivial"):
            continue
        if slug and row.get("slug") != slug:
            continue
        session = load_json(archive.normalized_dir / row["file"])
        for piece in split_session(session, splits):
            key = (row.get("slug") or "unknown", night_date(piece.get("startedAt")), night_part(piece.get("startedAt"), splits))
            groups.setdefault(key, []).append(piece)
    out = [build_night(v, part=k[2]) for k, v in groups.items()]
    out.sort(key=lambda n: n.get("startedAt") or 0)
    return out


def resolve_night(archive: Archive, ref: str) -> dict[str, Any] | None:
    """ref: latest | tonight | YYYY-MM-DD | a night id | a session id (its night)."""
    all_nights = nights(archive)
    if not all_nights:
        return None
    if ref in ("latest", "tonight", "last", ""):
        return all_nights[-1]
    for n in all_nights:
        if n["id"] == ref or n["nightDate"] == ref or ref in n["sessionIds"] or any(s.split("#")[0] == ref for s in n["sessionIds"]):
            return n
    matches = [n for n in all_nights if n["id"].startswith(ref) or any(s.startswith(ref) for s in n["sessionIds"])]
    return matches[0] if len(matches) == 1 else None


def nights_of_session(archive: Archive, session_id: str) -> list[dict[str, Any]]:
    """Every night that holds this session or a piece of it (a split session feeds two chapters)."""
    return [n for n in nights(archive) if any(s.split("#")[0] == session_id for s in n["sessionIds"])]


def chapter_number(archive: Archive, night: dict[str, Any]) -> int:
    slug = night.get("character", {}).get("slug")
    earlier = [n for n in nights(archive, slug) if (n.get("startedAt") or 0) < (night.get("startedAt") or 0)]
    return len(earlier) + 1
