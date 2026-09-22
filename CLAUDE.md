# CLAUDE.md — Rambleon

Rambleon is a **personal memory layer for World of Warcraft**. It quietly records the experience of playing and
turns a night in Azeroth into a permanent record: a timeline, a factual log, and an AI-written journal chapter.

## What Rambleon is NOT

- not a DPS meter, not a combat assistant, not a rotation helper
- not a leveling guide or quest helper
- not a general WoW database
- not automation of any kind (no movement, no ability use, no interaction with other players)

## The one question

When considering a feature or an event to record, ask: **"Will this help the player remember their adventure?"**
If it would not be interesting to read six months later, it probably does not belong. Memories, not telemetry.

## Architecture

```
WoW: Forever → Rambleon AddOn (Lua) → SavedVariables → ramble watch (Mac) → archive/ (immutable) → JSON → Markdown → AI journal
```

- `addon/Rambleon/` — the AddOn. Passive event listeners, an in-memory session, a parchment panel, `/ramble` commands.
- `companion/` — the Python CLI `ramble` (uv + typer). Watches SavedVariables, archives, exports, summarizes.
- `archive/` — **the source of truth**. Raw snapshots are never edited; normalized sessions never shrink. Gitignored.
- `exports/` — generated artifacts (Markdown, prompts, journals). Regenerable. Gitignored.
- `docs/` — `environment.md` (this Mac), `addon-api.md` (Forever client facts), `data-model.md`, `progress.md`.

## The Forever beta SavedVariables bug (read this)

On the current beta build, WoW **writes** AddOn SavedVariables but does **not restore** them on the next launch
(cold start, logout/login, usually `/reload`). Details and sources in `docs/addon-api.md`. Therefore:

- The AddOn treats every login as a potentially new session and never depends on restored data.
- `ramble watch` snapshots the file on every write. The archive owns history. A blank file never erases a session.
- Do not add in-game hacks that load SavedVariables through the addon-file loader. Design around the bug.

## Coding rules

**AddOn (Lua 5.1 syntax, retail 12.x-style API):**
- Register events only via `ns.SafeRegister` (pcall). Unknown events throw on this client.
- Everything stored under `RambleonDB` must be a string, number, boolean or table of those. Route values through
  `ns.Clean` / `ns.CleanString`; never store Secret Values.
- No combat data, no protected APIs, no automation. If Blizzard hides something, accept it.
- Keep chat quiet: one login line. Debug output only behind `/ramble debug on`.
- Never call `ReloadUI` without the user confirming via the END & SAVE popup.
- TOC: `Rambleon_Camelot.toc` (Interface 16001) is the Forever one; keep `Rambleon.toc` identical apart from `Forever.lua`.

**Companion (Python ≥ 3.11):**
- Never execute SavedVariables as Lua; use `luaparse.py`.
- Raw snapshot first, parse second. Atomic writes. Merge by session id; never shrink or delete.
- AI is optional: `ramble summarize` must always produce the prompt file even without the Claude CLI.
- Printed WTF paths go through `Paths.redact()` so the account folder name stays out of logs and docs.

**Journal writing:** only events that were recorded. Understated, observational, occasionally funny. No fabricated
fights, loot or feelings. Rules live in `companion/src/rambleon/prompts/journal.md`.

## Dev loop

```
edit addon/Rambleon/*.lua
scripts/test                      # luac -p, simulated session, pytest
ramble install                    # symlink is already in place; reruns are idempotent
/reload in WoW                    # or restart WoW if the addon was not loaded before
/ramble debug                     # paste the output (and any Lua errors) back here
```

- `ramble watch` must be running while playing (or run `ramble ingest` afterwards; the file survives until WoW's next flush).
- Lua errors: enable with `/console scriptErrors 1` in game.
- `scripts/bootstrap` installs uv, syncs the env and installs `ramble` globally.

## Command cheat sheet

In game: `/ramble`, `/ramble status`, `/ramble note <text>`, `/ramble mark`, `/ramble end`, `/ramble debug [on|off]`, `/ramble dump`.

On the Mac: `ramble doctor`, `ramble install [--copy]`, `ramble watch`, `ramble ingest`, `ramble status`,
`ramble sessions`, `ramble show latest`, `ramble export latest`, `ramble summarize latest [--no-ai]`.

## Roadmap markers

- Milestone 1 (now): loads, `/ramble`, session captured, `ramble export latest`.
- Milestone 2: make the in-game timeline pleasant; satisfying MARK MOMENT.
- Milestone 3: AI chapter + shareable recap.
- Future, not yet: character timeline, adventure map, people history, screenshot timeline, weekly recaps,
  share cards, web viewer, native Mac app, multiple characters, Retail/Classic.
