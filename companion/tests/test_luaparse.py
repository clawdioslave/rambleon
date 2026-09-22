import math
from pathlib import Path

import pytest

from rambleon.luaparse import LuaParseError, TornFile, parse, to_python

FIXTURES = Path(__file__).parent / "fixtures"


def test_blizzard_fixtures_parse():
    for name in ("Blizzard_GlueSavedVariables.lua", "Blizzard_DamageMeter.lua", "Blizzard_CombatLog.lua"):
        data = (FIXTURES / name).read_bytes()
        assert b"\r\n" in data  # real files are CRLF
        result = parse(data)
        assert isinstance(result, dict) and result


def test_glue_nil_globals():
    result = parse((FIXTURES / "Blizzard_GlueSavedVariables.lua").read_bytes())
    assert "g_collapsedServerAlert" in result and result["g_collapsedServerAlert"] is None


def test_damage_meter_shape():
    result = to_python(parse((FIXTURES / "Blizzard_DamageMeter.lua").read_bytes()))
    settings = result["DamageMeterPerCharacterSettings"]
    assert settings["windowDataList"][0]["shown"] is True
    assert settings["windowDataList"][0]["sessionType"] == 0


def test_simulated_session_fixture():
    result = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))
    db = result["RambleonDB"]
    assert db["schemaVersion"] == 1
    assert len(db["sessions"]) == 2
    first = db["sessions"][0]
    assert first["state"] == "ended"
    assert first["events"][0]["type"] == "SESSION_START"
    assert any(e["type"] == "NOTE" and "cursed" in e["text"] for e in first["events"])
    assert first["character"]["fullName"] == "Rambleon Birdsong"


def test_torn_file_detected():
    data = (FIXTURES / "Rambleon_simulated.lua").read_bytes()[:2500]
    with pytest.raises(TornFile):
        parse(data)


def test_edge_cases():
    text = 'x = {\r\n"a",\r\nnil,\r\n"c",\r\n[0] = 1,\r\n["k"] = -inf,\r\n[5] = 1.5e+10,\r\nn = -nan(ind),\r\n["s"] = "q\\"uote\\n|pipe\\65",\r\n}  -- comment\r\ny = nil\r\nz = true\r\n'
    result = parse(text)
    x = result["x"]
    assert x[1] == "a" and x[3] == "c" and 2 not in x
    assert x[0] == 1 and x["k"] == -math.inf and x[5] == 1.5e10
    assert math.isnan(x["n"])
    assert x["s"] == 'q"uote\n|pipeA'
    assert result["y"] is None and result["z"] is True


def test_positional_nil_keeps_indices():
    result = to_python(parse("t = { 1, nil, 3, }"))
    assert result["t"] == {"1": 1, "3": 3}  # not a 1..n list, so it stays a map


def test_syntax_error_is_not_torn():
    with pytest.raises(LuaParseError) as info:
        parse("x = { ]")
    assert not isinstance(info.value, TornFile)


def test_float_precision_roundtrip():
    result = parse("v = 299.9999694824219")
    assert result["v"] == 299.9999694824219
