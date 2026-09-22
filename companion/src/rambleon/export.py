"""Factual Markdown adventure log. No narrative, no invention."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .archive import atomic_write_bytes


def clock(t: int | None) -> str:
    if not t:
        return "—"
    return datetime.fromtimestamp(t).strftime("%-I:%M %p")


def long_date(t: int | None) -> str:
    return datetime.fromtimestamp(t).strftime("%B %-d, %Y") if t else "Unknown date"


def duration(seconds: int | None) -> str:
    seconds = int(seconds or 0)
    h, m = divmod(seconds // 60, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def place(ev: dict[str, Any]) -> str | None:
    return ev.get("subzone") or ev.get("zone")


def describe(ev: dict[str, Any]) -> str:
    t = ev.get("type")
    if t == "SESSION_START":
        return "Began the adventure" + (f" in {place(ev)}" if place(ev) else "")
    if t == "RESUMED":
        return "Picked the story back up"
    if t == "SESSION_END":
        return "Ended the adventure"
    if t == "ZONE_ENTER":
        if ev.get("subzone") and ev.get("zone"):
            return f"Entered {ev['subzone']} ({ev['zone']})"
        return f"Entered {ev.get('zone') or 'somewhere new'}"
    if t == "LEVEL_UP":
        return f"Reached Level {ev.get('level')}"
    if t == "QUEST_ACCEPTED":
        return f"Accepted \"{ev.get('title') or 'quest ' + str(ev.get('questID'))}\""
    if t == "QUEST_COMPLETED":
        return f"Completed \"{ev.get('title') or 'quest ' + str(ev.get('questID'))}\""
    if t == "DEATH":
        return f"Died in {place(ev) or 'the wilds'}"
    if t == "REVIVED":
        return "Back among the living"
    if t == "GROUP_JOIN":
        return f"Joined forces with {ev.get('name')}" + (f" ({ev['class']})" if ev.get("class") else "")
    if t == "GROUP_LEAVE":
        return f"Parted ways with {ev.get('name')}"
    if t == "INSTANCE_ENTER":
        return f"Entered {ev.get('name') or 'an instance'}"
    if t == "INSTANCE_EXIT":
        return "Left the instance"
    if t == "ACHIEVEMENT":
        return f"Earned achievement: {ev.get('name') or ev.get('id')}"
    if t == "SCREENSHOT":
        return "Took a screenshot"
    if t == "NOTE":
        return f"Note: \"{ev.get('text')}\""
    if t == "MARK":
        return "Marked moment" + (f" in {place(ev)}" if place(ev) else "")
    return str(t)


def render_markdown(session: dict[str, Any]) -> str:
    c = session.get("character", {})
    cnt = session.get("counters", {})
    name = c.get("displayName", "Unknown")
    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append("")
    meta = [long_date(session.get("startedAt")), f"Adventure duration: {duration(session.get('playedSeconds'))}"]
    if c.get("race") or c.get("class"):
        meta.append(f"{c.get('race', '')} {c.get('class', '')}".strip() + (f", Level {c.get('endLevel')}" if c.get("endLevel") else ""))
    lines.append("  ".join(f"{m}" for m in meta[:1]) + "  ")
    for m in meta[1:]:
        lines.append(m + "  ")
    if session.get("state") != "ended":
        lines.append("")
        lines.append("_This chapter was not formally ended; it was captured as last seen._")
    lines.append("")
    lines.append("## Journey")
    lines.append("")
    for ev in session.get("events", []):
        lines.append(f"* {clock(ev.get('t'))} — {describe(ev)}")
    lines.append("")
    lines.append("## Progress")
    lines.append("")
    levels = cnt.get("levelsGained", 0)
    if c.get("startLevel") and c.get("endLevel") and c["endLevel"] != c["startLevel"]:
        levels_text = f"{levels} ({c['startLevel']} → {c['endLevel']})"
    else:
        levels_text = str(levels)
    lines += [
        f"Levels gained: {levels_text}  ",
        f"Quests accepted: {cnt.get('questsAccepted', 0)}  ",
        f"Quests completed: {cnt.get('questsCompleted', 0)}  ",
        f"Deaths: {cnt.get('deaths', 0)}  ",
        f"Places visited: {len(session.get('zones', []))}  ",
        f"People adventured with: {len(session.get('people', []))}  ",
        f"Playtime: {duration(session.get('playedSeconds'))}",
    ]
    people = sorted(session.get("people", []), key=lambda p: -(p.get("seconds") or 0))
    if people:
        lines += ["", "## People Met", ""]
        for p in people:
            mins = int(round((p.get("seconds") or 0) / 60))
            cls = f" ({p['class']})" if p.get("class") else ""
            lines.append(f"* {p.get('name')}{cls} — {mins} minute{'s' if mins != 1 else ''}")
    zones = session.get("zones", [])
    if zones:
        lines += ["", "## Places", ""]
        for z in zones:
            label = f"{z.get('subzone')} ({z.get('zone')})" if z.get("subzone") else str(z.get("zone"))
            lines.append(f"* {label}")
    notes = [ev for ev in session.get("events", []) if ev.get("type") == "NOTE"]
    if notes:
        lines += ["", "## Notes", ""]
        for ev in notes:
            lines.append(f"* {clock(ev.get('t'))} — {ev.get('text')}")
    shots = session.get("screenshots", [])
    if shots:
        lines += ["", "## Screenshots", ""]
        for s in shots:
            near = ""
            idx = s.get("nearestEventIndex")
            if idx is not None and idx < len(session.get("events", [])):
                near = f" (near: {describe(session['events'][idx])})"
            lines.append(f"* {clock(s.get('takenAt'))} — `{s.get('archived') or s.get('path')}`{near}")
    lines += ["", "---", f"Session `{session.get('id')}` · schema {session.get('schemaVersion')} · Rambleon {session.get('client', {}).get('addonVersion', '?')}", ""]
    return "\n".join(lines)


def export_filename(session: dict[str, Any], suffix: str = "") -> str:
    started = session.get("startedAt") or 0
    day = datetime.fromtimestamp(started).strftime("%Y-%m-%d")
    return f"{day}-{session.get('character', {}).get('slug', 'unknown')}{suffix}.md"


def export_session(session: dict[str, Any], exports_dir: Path) -> Path:
    out = exports_dir / "markdown" / export_filename(session)
    if out.exists():
        # Several sessions on one day: keep them apart with the session's local start time.
        started = session.get("startedAt") or 0
        stamp = datetime.fromtimestamp(started).strftime("%H%M")
        candidate = out.with_name(out.stem + f"-{stamp}.md")
        try:
            existing = out.read_text(encoding="utf-8")
            if f"Session `{session.get('id')}`" not in existing:
                out = candidate
        except OSError:
            out = candidate
    atomic_write_bytes(out, render_markdown(session).encode("utf-8"))
    return out
