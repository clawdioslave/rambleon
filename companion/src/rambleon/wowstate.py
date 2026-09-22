"""Is the player still in the game? Cheap, read-only signals from the Mac side."""
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

LOGOUT_MARKERS = ("Client Object Manager Destroyed", "Client Destroy")
LOGIN_MARKERS = ("Character Login SEND", "Active Player Created")
_LINE = re.compile(r"^(\d{1,2})/(\d{1,2}) (\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+(.*)$")


def wow_running() -> bool:
    try:
        out = subprocess.run(["ps", "-axo", "command"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True  # unknown: assume still playing
    return any("/Contents/MacOS/World of Warcraft" in line for line in out.splitlines())


def _parse_time(month: str, day: str, hh: str, mm: str, ss: str, now: datetime) -> float:
    year = now.year
    dt = datetime(year, int(month), int(day), int(hh), int(mm), int(ss))
    if dt > now:  # log line from last December read in January
        dt = dt.replace(year=year - 1)
    return dt.timestamp()


def last_client_events(wow_dir: Path | None) -> tuple[float | None, float | None]:
    """(last logout time, last login time) from Logs/Client.log, or (None, None)."""
    if not wow_dir:
        return None, None
    log = wow_dir / "Logs" / "Client.log"
    try:
        lines = log.read_text(errors="replace").splitlines()[-400:]
    except OSError:
        return None, None
    now = datetime.now()
    logout = login = None
    for line in lines:
        m = _LINE.match(line)
        if not m:
            continue
        text = m.group(7)
        try:
            t = _parse_time(*m.groups()[:5], now)
        except ValueError:
            continue
        if any(k in text for k in LOGOUT_MARKERS):
            logout = t
        elif any(k in text for k in LOGIN_MARKERS):
            login = t
    return logout, login


def logged_out_since(wow_dir: Path | None, since: float) -> bool:
    """True when the player has clearly left: WoW quit, or the client log shows a logout after `since`
    with no login after it."""
    if not wow_running():
        return True
    logout, login = last_client_events(wow_dir)
    if logout and logout >= since - 5 and (login is None or login < logout):
        return True
    return False
