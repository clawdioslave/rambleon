import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.luaparse import parse, to_python
from rambleon.normalize import sessions_from_db
from rambleon.publish import build_chapters, export_html, lua_string, write_chapters_lua
from rambleon.summarize import build_prompt
from rambleon.export import render_recap

FIXTURES = Path(__file__).parent / "fixtures"


def test_lua_string_escaping():
    s = lua_string('he said "hi"\nnew|line\\')
    assert s == '"he said \\"hi\\"\\nnew||line\\\\"'


def test_publish_roundtrip(tmp_path):
    archive = Archive(tmp_path / "archive")
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    chapters = build_chapters(archive, tmp_path / "exports")
    assert len(chapters) == 1 and chapters[0]["number"] == 1
    assert "Ramble on." in chapters[0]["recap"]
    addon = tmp_path / "addon"; addon.mkdir()
    path = write_chapters_lua(chapters, addon)
    parsed = to_python(parse(path.read_bytes()))["RambleonChapters"]
    assert parsed[0]["id"].startswith("night-") and "Moonhoof" in parsed[0]["log"]
    assert parsed[0]["guid"] == s["character"]["guid"] and parsed[0]["slug"] == "rambleon-birdsong"
    page = export_html(s, archive, tmp_path / "exports")
    text = page.read_text()
    assert "<h1>Chapter 1" in text and "Travelled with Moonhoof" in text


def test_two_nights_of_one_character_are_numbered_in_order(tmp_path):
    """The client changed how it spells the name between builds; the same GUID must stay one character."""
    import copy
    archive = Archive(tmp_path / "archive")
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    first = sessions_from_db(db)[0]
    raw_second = copy.deepcopy(db["sessions"][0])
    raw_second["id"] = raw_second["id"].replace("_rambleon-birdsong", "_rambleon")
    raw_second["character"].update({"name": "Rambleon", "fullName": "Rambleon", "realmFromFullName": "Birdsong"})
    raw_second["character"].pop("displayName", None)
    raw_second["character"].pop("surname", None)
    day = 86400
    raw_second["startedAt"] += day; raw_second["endedAt"] += day; raw_second["lastSeen"] += day
    for ev in raw_second["events"]:
        ev["t"] += day
    second = sessions_from_db({"sessions": [raw_second]})[0]
    assert second["character"]["slug"] == "rambleon-birdsong"
    cap = {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"}
    archive.upsert_session(first, cap); archive.upsert_session(second, cap)
    archive.rebuild_index()
    chapters = build_chapters(archive, tmp_path / "exports")
    assert [c["number"] for c in chapters] == [1, 2]
    assert {c["slug"] for c in chapters} == {"rambleon-birdsong"}
    assert {c["guid"] for c in chapters} == {first["character"]["guid"]}
    assert chapters[0]["id"] != chapters[1]["id"] and all(c["id"].endswith("-rambleon-birdsong") for c in chapters)


def test_recap_wording():
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    recap = render_recap(s)
    assert "in Azeroth" not in recap and "deaths" not in recap and recap.rstrip().endswith("Ramble on.")


def test_voices():
    from rambleon.summarize import available_voices, build_prompt, load_voice
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    assert {"golden", "field-journal"} <= set(available_voices())
    assert "Christie Golden" in load_voice("golden")
    assert "{voice}" not in build_prompt(s, 1, "field-journal")
    assert "field journal" in build_prompt(s, 1, "field-journal")


def test_character_overrides(tmp_path, monkeypatch):
    from rambleon import summarize as sm
    (tmp_path / "rambleon.local.toml").write_text('[characters."rambleon-birdsong"]\ngender = "male"\n')
    monkeypatch.setattr("rambleon.config.find_repo_root", lambda: tmp_path)
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    s["character"].pop("gender", None)
    assert "Gender: male" in sm.build_prompt(s, 1, "field-journal")


# --- screenshots on the story page ---------------------------------------------------------------

import base64
import os
import shutil

from rambleon import publish as pub
from rambleon.screenshots import attach_screenshots

PNG_1x1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def session_with_shots(tmp_path):
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    wow_shots = tmp_path / "Screenshots"; wow_shots.mkdir()
    shots = [ev for ev in s["events"] if ev["type"] == "SCREENSHOT"]
    for n, ev in enumerate(shots):
        p = wow_shots / f"WoWScrnShot_092226_2000{n:02d}.png"
        p.write_bytes(PNG_1x1)
        os.utime(p, (ev["t"], ev["t"]))
    attach_screenshots(s, wow_shots, tmp_path / "archive" / "screenshots")
    return s


def test_story_page_shows_pictures_in_a_gallery_without_a_timeline(tmp_path, monkeypatch):
    monkeypatch.setattr(pub, "RESIZER", None)
    s = session_with_shots(tmp_path)
    archive = Archive(tmp_path / "archive")
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    page = export_html(s, archive, tmp_path / "exports")
    text = page.read_text()
    assert "<figure class='hero'>" in text and "Marked moment in Dolanaar" in text
    assert f"<figure class='hero'><img src='{page.stem}/{page.stem}-02.png' alt='Reached Level 11 in Dolanaar'" in text
    assert "<h2>Pictures</h2><div class='gallery'>" in text and text.count("<figure>") == 4   # five pictures: one hero, four in the gallery
    assert "The Journey" not in text and "<li>" not in text          # the chapter is the journey: no event timeline
    assert " AM — " not in text and " PM — " not in text and "Deaths" not in text and "in Azeroth" not in text
    assert "Screenshots</h2>" not in text and "Took a screenshot" not in text
    assert str(tmp_path) not in text and "WoWScrnShot_" not in text
    assert sorted(p.name for p in page.with_suffix("").iterdir()) == [f"{page.stem}-0{n}.png" for n in range(1, 6)]
    index = pub.write_html_index(archive, tmp_path / "exports")
    assert "class='thumb'" in index.read_text()
    assert "class='thumb'" not in pub.write_html_index(archive, tmp_path / "exports", only=set()).read_text()


def test_web_copies_are_jpeg_when_sips_is_available(tmp_path):
    if not shutil.which("sips"):
        import pytest
        pytest.skip("sips is macOS only")
    s = session_with_shots(tmp_path)
    images = pub.prepare_images(s, tmp_path / "web" / "2026-09-22-x")
    assert [i["src"] for i in images] == [f"2026-09-22-x/2026-09-22-x-0{n}.jpg" for n in range(1, 6)]
    first = tmp_path / "web" / "2026-09-22-x" / "2026-09-22-x-01.jpg"
    assert first.read_bytes()[:2] == b"\xff\xd8"
    stamp = first.stat().st_mtime_ns
    pub.prepare_images(s, tmp_path / "web" / "2026-09-22-x")
    assert first.stat().st_mtime_ns == stamp                     # unchanged source → no rewrite


def test_prompt_tells_the_writer_when_pictures_were_taken(tmp_path):
    s = session_with_shots(tmp_path)
    prompt = build_prompt(s, 1)
    assert "screenshot taken when: Reached Level 11 in Dolanaar at" in prompt
    assert str(tmp_path) not in prompt


def test_tga_without_sips_is_skipped_not_broken(tmp_path, monkeypatch):
    monkeypatch.setattr(pub, "RESIZER", None)
    src = tmp_path / "WoWScrnShot_092226_200000.tga"; src.write_bytes(b"\x00" * 18)
    s = {"events": [], "screenshots": [{"path": str(src), "file": src.name, "takenAt": 1}]}
    assert pub.prepare_images(s, tmp_path / "web" / "p") == []
    assert not (tmp_path / "web" / "p").exists() or not list((tmp_path / "web" / "p").iterdir())
