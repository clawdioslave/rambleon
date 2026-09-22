import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.paths import Paths
from rambleon.watch import ingest_once, process_file, watch

FIXTURES = Path(__file__).parent / "fixtures"


def fake_wow(tmp_path: Path) -> tuple[Paths, Path]:
    wow = tmp_path / "wow"
    sv_dir = wow / "WTF" / "Account" / "123#1" / "70" / "Rambleon-Birdsong" / "SavedVariables"
    sv_dir.mkdir(parents=True)
    (wow / "Interface" / "AddOns").mkdir(parents=True)
    paths = Paths(repo_root=tmp_path, wow_dir=wow, archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    return paths, sv_dir / "Rambleon.lua"


def test_ingest_archives_sessions(tmp_path):
    paths, sv = fake_wow(tmp_path)
    sv.write_bytes((FIXTURES / "Rambleon_simulated.lua").read_bytes())
    archive = Archive(paths.archive_dir)
    logs = []
    outcomes = ingest_once(paths, archive, logs.append)
    assert len(outcomes) == 2 and all(o.startswith("new") for o in outcomes)
    assert len(list(archive.raw_dir.glob("*_Rambleon.lua"))) == 1
    assert len(archive.session_files()) == 2
    # same bytes again → nothing happens
    assert ingest_once(paths, archive, logs.append) == []
    # a blank DB (the beta bug) never touches the archive
    sv.write_bytes(b"\r\nRambleonDB = {\r\n[\"schemaVersion\"] = 1,\r\n[\"sessions\"] = {\r\n},\r\n}\r\n")
    assert ingest_once(paths, archive, logs.append) == ["empty"]
    assert len(archive.session_files()) == 2


def test_torn_file_falls_back_to_bak(tmp_path):
    paths, sv = fake_wow(tmp_path)
    good = (FIXTURES / "Rambleon_simulated.lua").read_bytes()
    sv.with_name("Rambleon.lua.bak").write_bytes(good)
    sv.write_bytes(good[:1500])
    archive = Archive(paths.archive_dir)
    logs = []
    outcomes = process_file(sv, paths, archive, logs.append)
    assert any(o.startswith("new") for o in outcomes)
    assert list(archive.failed_dir.glob("*_Rambleon.lua"))
    assert any("could not parse" in m for m in logs)


def test_watch_loop_picks_up_a_write(tmp_path):
    paths, sv = fake_wow(tmp_path)
    archive = Archive(paths.archive_dir)
    logs = []
    import threading
    def writer():
        time.sleep(0.5)
        sv.write_bytes((FIXTURES / "Rambleon_simulated.lua").read_bytes())
    threading.Thread(target=writer).start()
    watch(paths, archive, logs.append, interval=0.2, stop_after=3.0, rescan=0.5)
    assert len(archive.session_files()) == 2
    assert not archive.pid_path.exists()
