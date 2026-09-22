"""Turn a parsed RambleonDB table into clean, stable session dicts ready for JSON."""
from __future__ import annotations

import time
from typing import Any

from .luaparse import to_python
from .model import COUNTER_KEYS, NORMALIZED_VERSION, SUSPEND_TIMEOUT, slugify, validate_session


def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v == v:
        return int(v)
    return None


def _as_list(v: Any) -> list[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        keys = sorted(k for k in v.keys() if str(k).lstrip("-").isdigit())
        return [v[k] for k in keys]
    return []


def sessions_from_db(db: Any) -> list[dict[str, Any]]:
    """db is the value of the RambleonDB global (parsed dict or to_python output)."""
    db = to_python(db) if isinstance(db, dict) and any(isinstance(k, int) for k in db) else db
    if not isinstance(db, dict):
        return []
    out: list[dict[str, Any]] = []
    for raw in _as_list(db.get("sessions")):
        s = normalize_session(raw, addon_version=db.get("addonVersion"), db_schema=db.get("schemaVersion"))
        if s is not None:
            out.append(s)
    return out


def normalize_session(raw: Any, addon_version: Any = None, db_schema: Any = None, now: float | None = None) -> dict[str, Any] | None:
    raw = to_python(raw) if isinstance(raw, dict) and any(isinstance(k, int) for k in raw) else raw
    if not isinstance(raw, dict):
        return None
    s: dict[str, Any] = {}
    s["schemaVersion"] = _int(raw.get("schemaVersion")) or _int(db_schema) or 1
    s["normalizedVersion"] = NORMALIZED_VERSION
    s["id"] = raw.get("id") if isinstance(raw.get("id"), str) else None
    s["addonState"] = raw.get("state")
    s["startedAt"] = _int(raw.get("startedAt"))
    s["startedServerTime"] = _int(raw.get("startedServerTime"))
    s["endedAt"] = _int(raw.get("endedAt"))
    s["lastSeen"] = _int(raw.get("lastSeen"))
    s["playedSeconds"] = _int(raw.get("playedSeconds")) or 0
    s["endReason"] = raw.get("endReason") if isinstance(raw.get("endReason"), str) else None
    s["resumes"] = _int(raw.get("resumes")) or 0

    character = raw.get("character") if isinstance(raw.get("character"), dict) else {}
    s["character"] = {k: v for k, v in character.items() if isinstance(v, (str, int, float, bool))}
    s["character"]["displayName"] = character.get("fullName") or character.get("name") or "Unknown"
    s["character"]["slug"] = slugify(s["character"]["displayName"])
    client = raw.get("client") if isinstance(raw.get("client"), dict) else {}
    s["client"] = {k: v for k, v in client.items() if isinstance(v, (str, int, float, bool))}
    if addon_version and "addonVersion" not in s["client"]:
        s["client"]["addonVersion"] = addon_version

    counters = raw.get("counters") if isinstance(raw.get("counters"), dict) else {}
    s["counters"] = {k: (_int(counters.get(k)) or 0) for k in COUNTER_KEYS}

    events: list[dict[str, Any]] = []
    for ev in _as_list(raw.get("events")):
        if isinstance(ev, dict) and isinstance(ev.get("type"), str) and _int(ev.get("t")) is not None:
            clean = {k: v for k, v in ev.items() if isinstance(v, (str, int, float, bool))}
            clean["t"] = _int(ev["t"])
            events.append(clean)
    events.sort(key=lambda e: e["t"])  # stable: preserves insertion order for equal timestamps
    s["events"] = events

    s["zones"] = [z for z in _as_list(raw.get("zones")) if isinstance(z, dict)]
    s["people"] = [p for p in _as_list(raw.get("people")) if isinstance(p, dict)]
    s["failedEvents"] = [e for e in _as_list(raw.get("failedEvents")) if isinstance(e, str)]
    kills = raw.get("kills") if isinstance(raw.get("kills"), dict) else {}
    s["kills"] = {str(name): {k: _int(v) for k, v in info.items() if _int(v) is not None}
                  for name, info in kills.items() if isinstance(info, dict)}

    # Effective state: a suspended session nobody resumed is over.
    now = now if now is not None else time.time()
    state = raw.get("state")
    if state == "ended":
        s["state"] = "ended"
    elif state in ("suspended", "active"):
        last = s["lastSeen"] or s["startedAt"] or 0
        if now - last > SUSPEND_TIMEOUT:
            s["state"] = "ended"
            s["endedAt"] = s["endedAt"] or last
            s["endReason"] = s["endReason"] or ("logout" if state == "suspended" else "unknown")
        else:
            s["state"] = "suspended"
    else:
        s["state"] = "suspended"
    if s["state"] == "ended" and not s["endedAt"]:
        s["endedAt"] = s["lastSeen"] or s["startedAt"]
    if not s["playedSeconds"] and s["startedAt"] and s["endedAt"]:
        s["playedSeconds"] = max(0, s["endedAt"] - s["startedAt"])

    problems = validate_session({**s, "state": s["state"]})
    if problems:
        return None
    return s
