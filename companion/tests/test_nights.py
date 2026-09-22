import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.luaparse import parse, to_python
from rambleon.nights import build_night, night_date, nights, resolve_night
from rambleon.normalize import sessions_from_db
from rambleon.export import render_markdown
from rambleon.watch import Finalizer

FIXTURES = Path(__file__).parent / "fixtures"


def two_sessions():
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    a = sessions_from_db(db)[0]
    b = dict(a, id=a["id"] + "-later", startedAt=a["startedAt"] + 3600, endedAt=a["endedAt"] + 3600,
             events=[dict(e, t=e["t"] + 3600) for e in a["events"]])
    return a, b


def test_night_stitches_sessions(tmp_path):
    a, b = two_sessions()
    night = build_night([a, b])
    assert night["kind"] == "night" and night["sessionIds"] == [a["id"], b["id"]]
    assert night["playedSeconds"] == a["playedSeconds"] * 2
    assert night["counters"]["kills"] == a["counters"]["kills"] * 2
    assert night["kills"]["Timberling"]["count"] == a["kills"]["Timberling"]["count"] * 2
    assert len(night["people"]) == 1 and night["people"][0]["seconds"] == a["people"][0]["seconds"] * 2
    types = [e["type"] for e in night["events"]]
    assert types.count("SESSION_START") == 1 and "RESUMED" not in types
    assert types.count("SESSION_END") == [e["type"] for e in b["events"]].count("SESSION_END")
    assert night["character"]["startLevel"] == 10 and night["character"]["endLevel"] == a["character"]["endLevel"]
    md = render_markdown(night)
    assert "Picked the story back up" not in md


def test_night_cutoff():
    import datetime
    late = int(datetime.datetime(2026, 9, 22, 1, 30).timestamp())
    assert night_date(late) == "2026-09-21"


def test_nights_from_archive_and_resolve(tmp_path):
    archive = Archive(tmp_path / "archive")
    a, b = two_sessions()
    cap = {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"}
    archive.upsert_session(a, cap); archive.upsert_session(b, cap); archive.rebuild_index()
    ns = nights(archive)
    assert len(ns) == 1 and len(ns[0]["sessionIds"]) == 2
    assert resolve_night(archive, "latest")["id"] == ns[0]["id"]
    assert resolve_night(archive, b["id"])["id"] == ns[0]["id"]
    assert resolve_night(archive, ns[0]["nightDate"])["id"] == ns[0]["id"]


def test_finalizer_waits_for_logout():
    runs = []
    fin = Finalizer(runs.append, lambda m: None, timeout=0.2)
    a, _ = two_sessions()
    fin.on_capture(dict(a, state="suspended"))
    fin.tick()
    assert runs == []
    time.sleep(0.4)
    fin.tick()
    assert len(runs) == 1
    fin.on_capture(dict(a, state="ended"))
    assert len(runs) == 2
