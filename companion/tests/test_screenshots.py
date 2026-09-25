import os
import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.luaparse import parse, to_python
from rambleon.nights import build_night
from rambleon.normalize import sessions_from_db
from rambleon.paths import Paths
from rambleon.screenshots import attach_screenshots, caption, pair_screenshots, refresh_session_screenshots

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_session():
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    return sessions_from_db(db)[0]


def shot_events(session):
    return [(i, ev) for i, ev in enumerate(session["events"]) if ev["type"] == "SCREENSHOT"]


def fake_file(directory: Path, taken: int, n: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"WoWScrnShot_092226_2000{n:02d}.jpg"
    p.write_bytes(b"\xff\xd8fake")
    os.utime(p, (taken, taken))
    return p


def test_files_pair_with_screenshot_events_and_inherit_reasons(tmp_path):
    s = fixture_session()
    shots = shot_events(s)
    assert [ev["reason"] for _, ev in shots] == ["ZONE_ENTER", "LEVEL_UP", "MARK", "MARK", "MANUAL"]
    wow_shots = tmp_path / "Screenshots"
    for n, (_, ev) in enumerate(shots):
        fake_file(wow_shots, ev["t"] + 1, n)      # the file lands a second before the event is stamped
    attach_screenshots(s, wow_shots, tmp_path / "archive" / "screenshots")
    got = s["screenshots"]
    assert [g["reason"] for g in got] == ["ZONE_ENTER", "LEVEL_UP", "MARK", "MARK", "MANUAL"]
    assert [g["eventIndex"] for g in got] == [i for i, _ in shots]
    assert got[0]["caption"] == "Entered Darkshore"
    assert got[1]["caption"] == "Reached Level 11 in Dolanaar" and got[1]["level"] == 11 and got[1]["auto"] is True
    assert got[2]["caption"] == got[3]["caption"] == "Marked moment in Dolanaar"
    assert got[4]["caption"] == "Screenshot in Dolanaar" and "auto" not in got[4]
    for g in got:
        assert Path(g["archived"]).exists() and g["archived"].startswith(str(tmp_path / "archive" / "screenshots" / s["id"]))
    assert "nearestEventIndex" not in got[0]


def test_late_file_falls_back_to_nearest_ordinary_event(tmp_path):
    s = fixture_session()
    wow_shots = tmp_path / "Screenshots"
    late = (s.get("endedAt") or s["lastSeen"]) + 40
    fake_file(wow_shots, late, 1)
    attach_screenshots(s, wow_shots)
    (shot,) = s["screenshots"]
    assert shot.get("reason") is None
    assert s["events"][shot["eventIndex"]]["type"] not in ("SCREENSHOT", "SESSION_END", "RESUMED")
    assert shot["caption"].startswith("Screenshot")
    assert "archived" not in shot


def test_one_file_per_event_and_vanished_sources_are_kept(tmp_path):
    s = fixture_session()
    idx, ev = shot_events(s)[1]
    wow_shots = tmp_path / "Screenshots"
    fake_file(wow_shots, ev["t"], 1)
    fake_file(wow_shots, ev["t"] + 2, 2)          # a manual shot right after the automatic one
    attach_screenshots(s, wow_shots)
    a, b = s["screenshots"]
    assert a["eventIndex"] == idx and b["eventIndex"] != idx
    for p in wow_shots.iterdir():
        p.unlink()
    attach_screenshots(s, wow_shots)
    assert len(s["screenshots"]) == 2


def test_refresh_pairs_files_that_arrived_after_capture(tmp_path):
    s = fixture_session()
    paths = Paths(repo_root=tmp_path, wow_dir=tmp_path / "wow", archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    archive = Archive(paths.archive_dir)
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    _, ev = shot_events(s)[1]
    fake_file(paths.screenshots_dir, ev["t"], 1)
    assert refresh_session_screenshots(archive, paths, [s["id"]]) == 1
    again = archive.load_session(s["id"])
    assert again["screenshots"][0]["caption"] == "Reached Level 11 in Dolanaar"
    assert again["archive"]["rawSnapshot"] == "x" and again["archive"]["revision"] == 2
    assert refresh_session_screenshots(archive, paths, [s["id"]]) == 0


def test_night_repairs_over_the_merged_timeline():
    a = fixture_session()
    b = dict(a, id=a["id"] + "-later", startedAt=a["startedAt"] + 3600, endedAt=a["endedAt"] + 3600,
             events=[dict(e, t=e["t"] + 3600) for e in a["events"]])
    idx, ev = shot_events(b)[1]
    b["screenshots"] = [{"path": "/gone/x.jpg", "file": "WoWScrnShot_092226_210000.jpg", "takenAt": ev["t"]}]
    a["screenshots"] = []
    night = build_night([a, b])
    (shot,) = night["screenshots"]
    paired = night["events"][shot["eventIndex"]]
    assert paired["type"] == "SCREENSHOT" and paired["t"] == ev["t"] and shot["caption"] == "Reached Level 11 in Dolanaar"
    assert b["screenshots"][0].get("eventIndex") is None   # the session's own entry is untouched


def test_caption_without_events():
    assert caption({"reason": "LEVEL_UP", "level": 3}, []) == "Reached Level 3"
    assert caption({"reason": "ZONE_ENTER", "zone": "Darkshore"}, []) == "Entered Darkshore"
    assert caption({}, []) == "Screenshot"
    shots = [{"file": "a", "takenAt": 100}]
    pair_screenshots(shots, [])
    assert shots[0]["eventIndex"] is None and shots[0]["caption"] == "Screenshot"
