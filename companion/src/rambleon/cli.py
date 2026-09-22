"""The `ramble` command."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .archive import Archive
from .doctor import run_doctor
from .export import duration, export_session, render_markdown
from .install import install_addon
from .paths import resolve_paths
from .nights import nights as list_nights, resolve_night
from .publish import export_html, publish_chapters
from .watch import Finalizer
from .summarize import DEFAULT_MODEL, summarize as run_summarize
from .watch import ingest_once, reprocess as run_reprocess, watch as run_watch

app = typer.Typer(help="Rambleon — your Azeroth adventure journal, Mac side.", no_args_is_help=True, add_completion=False)
console = Console()


def log(msg: str) -> None:
    console.print(f"[dim]{datetime.now():%H:%M:%S}[/dim] {msg}", highlight=False)


def _archive() -> tuple[Archive, "Paths"]:  # type: ignore[name-defined]
    paths = resolve_paths()
    archive = Archive(paths.archive_dir)
    archive.ensure()
    return archive, paths


def _load(ref: str) -> dict:
    archive, _ = _archive()
    session = archive.load_session(ref)
    if session is None:
        console.print(f"[red]no archived session matches {ref!r}[/red] — try `ramble sessions`")
        raise typer.Exit(1)
    return session


def _night(ref: str) -> dict:
    """A chapter = a night. ref: latest | tonight | YYYY-MM-DD | night id | session id."""
    archive, _ = _archive()
    night = resolve_night(archive, ref)
    if night is None:
        console.print(f"[red]no night matches {ref!r}[/red] — try `ramble nights`")
        raise typer.Exit(1)
    return night


@app.command()
def version() -> None:
    """Print the companion version."""
    console.print(f"ramble {__version__}")


@app.command()
def doctor() -> None:
    """Check WoW, the AddOn, SavedVariables, the archive and the AI adapter."""
    paths = resolve_paths()
    checks = run_doctor(paths)
    width = max(len(c.label) for c in checks) + 1
    for c in checks:
        color = "green" if c.ok else "red"
        console.print(f"{c.label + ':':<{width}} [{color}]{c.status}[/{color}]  [dim]{c.detail}[/dim]", highlight=False)
    if any(not c.ok and c.essential for c in checks):
        raise typer.Exit(1)


@app.command()
def install(copy: bool = typer.Option(False, "--copy", help="Copy the AddOn instead of symlinking it.")) -> None:
    """Link (or copy) the AddOn into the WoW Forever AddOns folder."""
    paths = resolve_paths()
    try:
        console.print(install_addon(paths, copy=copy))
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print("Now /reload in WoW (or restart it if Rambleon was not loaded before).")


def _finish_night(archive: Archive, paths, use_ai: bool, model: str):
    """What happens when a night is over: export, journal, HTML, publish to the game."""
    def run(session: dict) -> None:
        night = resolve_night(archive, session["id"]) or session
        md = export_session(night, paths.exports_dir)
        log(f"exported {md.name}")
        if use_ai:
            run_summarize(night, archive, paths.exports_dir, use_ai=True, model=model, log=log)
        page = export_html(night, archive, paths.exports_dir)
        log(f"story page {page}")
        _, n = publish_chapters(archive, paths)
        log(f"published {n} chapter(s) to the game — they show under /ramble chapters after the next login or /reload")
    return run


@app.command()
def watch(interval: float = typer.Option(1.0, help="Seconds between polls."),
          copy_screenshots: bool = typer.Option(False, "--copy-screenshots", help="Copy matching screenshots into the archive."),
          no_ai: bool = typer.Option(False, "--no-ai", help="Do not call the Claude CLI when a chapter ends."),
          no_auto: bool = typer.Option(False, "--no-auto", help="Only archive; skip export/journal/publish."),
          model: str = typer.Option(DEFAULT_MODEL, "--model")) -> None:
    """Watch SavedVariables and archive every session WoW writes. Leave this running while you play.
    When a chapter ends it also exports it, writes the journal, builds the story page and publishes it to the game."""
    archive, paths = _archive()
    if paths.wow_dir is None:
        console.print("[red]WoW directory not found[/red] (set RAMBLEON_WOW_DIR)")
        raise typer.Exit(1)
    finalizer = None if no_auto else Finalizer(_finish_night(archive, paths, use_ai=not no_ai, model=model), log)
    try:
        run_watch(paths, archive, log, interval=interval, copy_screenshots=copy_screenshots,
                  after_capture=finalizer.on_capture if finalizer else None, tick=finalizer.tick if finalizer else None)
    except KeyboardInterrupt:
        console.print("\nstopped.")


@app.command()
def publish() -> None:
    """Write the latest chapters into the AddOn (Chapters.lua) so /ramble chapters can show them in game."""
    archive, paths = _archive()
    path, n = publish_chapters(archive, paths)
    console.print(f"published {n} chapter(s) → {path}. In WoW: /reload, then /ramble chapters.")


@app.command()
def nights() -> None:
    """List chapters: one per night, per character."""
    archive, _ = _archive()
    rows = list_nights(archive)
    if not rows:
        console.print("no nights archived yet.")
        return
    table = Table(box=None, header_style="bold")
    for col in ("Night", "Character", "Duration", "Lv", "Quests", "Places", "Kills", "Deaths", "People", "Sessions", "State"):
        table.add_column(col)
    for n in rows:
        c = n["counters"]; ch = n["character"]
        lv = f"{ch.get('startLevel', '?')}→{ch.get('endLevel', '?')}" if ch.get("startLevel") != ch.get("endLevel") else str(ch.get("endLevel", "?"))
        table.add_row(n["nightDate"], str(ch.get("displayName")), duration(n.get("playedSeconds")), lv, str(c.get("questsCompleted", 0)),
                      str(len(n["zones"])), str(c.get("kills", 0)), str(c.get("deaths", 0)), str(len(n["people"])),
                      str(len(n["sessionIds"])), n["state"])
    console.print(table)


@app.command()
def page(ref: str = typer.Argument("latest"), open_it: bool = typer.Option(True, "--open/--no-open")) -> None:
    """Build the HTML story page for a night (journal, recap, screenshots, timeline) and open it in the browser."""
    archive, paths = _archive()
    session = _night(ref)
    out = export_html(session, archive, paths.exports_dir)
    console.print(f"story page {out}")
    if open_it and sys.platform == "darwin":
        subprocess.run(["open", str(out)], check=False)


@app.command()
def ingest(copy_screenshots: bool = typer.Option(False, "--copy-screenshots")) -> None:
    """Archive whatever Rambleon SavedVariables exist right now (one pass, no watching)."""
    archive, paths = _archive()
    outcomes = ingest_once(paths, archive, log, copy_screenshots)
    if outcomes:
        console.print(f"{len(outcomes)} outcome(s): " + ", ".join(outcomes))
    else:
        console.print("nothing new.")


@app.command()
def reprocess(copy_screenshots: bool = typer.Option(False, "--copy-screenshots")) -> None:
    """Rebuild normalized sessions from the archived raw snapshots (use after upgrading the companion)."""
    archive, paths = _archive()
    run_reprocess(paths, archive, log, copy_screenshots)


@app.command()
def status() -> None:
    """Archive overview and the latest session."""
    archive, paths = _archive()
    sessions = archive.list_sessions()
    pid = archive.watcher_pid()
    console.print(f"Archive: {paths.archive_dir} — {len(sessions)} session(s)")
    console.print(f"Watcher: {'running (pid ' + str(pid) + ')' if pid else 'not running'}")
    sv = paths.saved_variables_files()
    if sv:
        newest = max(sv, key=lambda p: p.stat().st_mtime)
        console.print(f"SavedVariables last written: {datetime.fromtimestamp(newest.stat().st_mtime):%Y-%m-%d %H:%M:%S}")
    total = sum(s.get("playedSeconds") or 0 for s in sessions)
    if sessions:
        console.print(f"Total time in Azeroth (archived): {duration(total)}")
        s = sessions[-1]
        console.print(f"Latest: {s['character']} — {datetime.fromtimestamp(s['startedAt']):%B %-d, %Y %-I:%M %p} — "
                      f"{duration(s.get('playedSeconds'))} — {s['events']} events — {s['state']}")


@app.command()
def sessions() -> None:
    """List archived sessions."""
    archive, _ = _archive()
    rows = archive.list_sessions()
    if not rows:
        console.print("no sessions archived yet.")
        return
    table = Table(box=None, header_style="bold")
    for col in ("When", "Character", "Duration", "Lv", "Quests", "Places", "Deaths", "People", "Events", "State", "Session ID"):
        table.add_column(col)
    for s in rows:
        c = s.get("counters", {})
        lv = f"{s.get('startLevel', '?')}→{s.get('endLevel', '?')}" if s.get("startLevel") != s.get("endLevel") else str(s.get("endLevel", "?"))
        table.add_row(datetime.fromtimestamp(s["startedAt"]).strftime("%Y-%m-%d %H:%M"), str(s.get("character")),
                      duration(s.get("playedSeconds")), lv, str(c.get("questsCompleted", 0)), str(c.get("zonesVisited", 0)),
                      str(c.get("deaths", 0)), str(s.get("people", 0)), str(s.get("events")),
                      ("trivial" if s.get("trivial") else str(s.get("state"))), str(s.get("id")))
    console.print(table)


@app.command()
def show(ref: str = typer.Argument("latest"), as_json: bool = typer.Option(False, "--json")) -> None:
    """Show one session (default: latest) as a factual log, or as JSON."""
    session = _load(ref)
    if as_json:
        console.print_json(json.dumps(session))
    else:
        console.print(render_markdown(session), markup=False, highlight=False)


@app.command()
def export(ref: str = typer.Argument("latest"), all_nights: bool = typer.Option(False, "--all")) -> None:
    """Write the factual Markdown log of a night (latest | tonight | YYYY-MM-DD | session id) to exports/markdown/."""
    archive, paths = _archive()
    targets = list_nights(archive) if all_nights else [_night(ref)]
    for night in targets:
        out = export_session(night, paths.exports_dir)
        console.print(f"exported {out}")


@app.command()
def summarize(ref: str = typer.Argument("latest"),
              no_ai: bool = typer.Option(False, "--no-ai", help="Only write the prompt; do not call the Claude CLI."),
              model: str = typer.Option(DEFAULT_MODEL, "--model")) -> None:
    """Write the journal prompt for a night and, if the Claude CLI is available, the AI-written chapter."""
    archive, paths = _archive()
    session = _night(ref)
    result = run_summarize(session, archive, paths.exports_dir, use_ai=not no_ai, model=model, log=log)
    for k, v in result.items():
        if v:
            console.print(f"{k}: {v}")
    page_path = export_html(session, archive, paths.exports_dir)
    console.print(f"story page: {page_path}")
    _, n = publish_chapters(archive, paths)
    console.print(f"published {n} chapter(s) to the game — /reload in WoW, then /ramble chapters")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
