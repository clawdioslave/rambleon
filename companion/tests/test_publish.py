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
    page = export_html(s, archive, tmp_path / "exports")
    text = page.read_text()
    assert "<h1>Chapter 1" in text and "Travelled with Moonhoof" in text


def test_recap_wording():
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    recap = render_recap(s)
    assert recap.startswith("6m in Azeroth tonight.") and recap.rstrip().endswith("Ramble on.")


def test_voices():
    from rambleon.summarize import available_voices, build_prompt, load_voice
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    assert {"golden", "field-journal"} <= set(available_voices())
    assert "Christie Golden" in load_voice("golden")
    assert "{voice}" not in build_prompt(s, 1, "field-journal")
    assert "field journal" in build_prompt(s, 1, "field-journal")
