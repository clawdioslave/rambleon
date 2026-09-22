# Progress

## 2026-09-21 — Day one

Goal: first playable milestone (AddOn loads, `/ramble` works, a session is captured, `ramble export latest` produces Markdown).

### Done
- Inspected the Mac and the WoW: Forever install (`environment.md`). Only `_classic_beta_` (1.60.1.69913) is installed.
- Researched the Forever client: mainline 12.x codebase, TOC `16001`, `_Camelot` suffix, `WOW_PROJECT_ID` = mainline,
  Secret Values, missing spec APIs, `RegisterEvent` throwing on unknown events (`addon-api.md`).
- Researched and documented the SavedVariables restore bug on build 69913 (`addon-api.md`); designed around it:
  every login is a new session, the Mac archive owns history, blank files never erase anything.
- Repository, `.gitignore`, git initialised.
- **AddOn v0.1.0** (`addon/Rambleon`): `Rambleon_Camelot.toc` + `Rambleon.toc`, session model (schema 1), events
  (zones with debounce, levels, quests, deaths, group roster + time together, instances, achievements, screenshots),
  manual notes and marks, parchment panel with stats + recent journey + MARK MOMENT / ADD NOTE / END CHAPTER,
  `/ramble` commands (`status`, `note`, `mark`, `end`, `debug`, `dump`), keybindings, END & SAVE popup with
  `/reload` fallback. Symlinked into `_classic_beta_/Interface/AddOns/Rambleon`.
- Offline harness: `addon/tests/wowstub.lua` + `run.lua` simulate a full session under Lua 5.5 and emit a
  Blizzard-format SavedVariables fixture.
- **Companion v0.1.0** (`companion/`, `ramble`): `doctor`, `install`, `watch`, `ingest`, `status`, `sessions`, `show`,
  `export`, `summarize`. Hand-written SavedVariables parser (verified on all 38 real Blizzard SV files on this Mac,
  plus torn-file detection), immutable archive with merge rules, polling watcher, screenshot pairing, factual
  Markdown export, AI-neutral prompt + Claude CLI adapter. 19 pytest cases. `uv tool install` → `ramble` on PATH.
- `ramble doctor` on this Mac: WoW Forever FOUND, AddOn INSTALLED (symlink, TOC 16001), Archive READY, Claude CLI FOUND.
- Docs: `environment.md`, `addon-api.md`, `data-model.md`, `CLAUDE.md`, `README.md`.

### Known issue found tonight
- The standalone `claude` CLI on this Mac reports "OAuth access token has been revoked", so `ramble summarize` skipped
  the AI chapter and only wrote the prompt (correct degraded behaviour). Fix on the Mac: run `claude` in a terminal
  and `/login`, then `ramble summarize latest` again.

### Next: first in-game test (needs the player)
1. `ramble watch` in a terminal.
2. Log in as Rambleon Birdsong. If Rambleon is greyed out in the AddOns list, enable "Load out of date AddOns" and
   report the interface number the game expects.
3. `/ramble` → panel titled RAMBLEON BIRDSONG. Walk somewhere new, accept/finish a quest, `/ramble mark`,
   `/ramble note hello from azeroth`, `/ramble debug` (paste the output).
4. END CHAPTER → END & SAVE. If the UI does not reload, type `/reload`.
5. The watcher prints `captured …`. Then `ramble export latest` and `ramble summarize latest`.

### Open questions (resolve on first in-game test)
- What `UnitFullName("player")` / `GetRealmName()` return on Forever for a two-part name (`/ramble debug`, session JSON).
- Whether `C_UI.Reload()` works from the END & SAVE button or is protected on Forever.
- Whether `QUEST_TURNED_IN` fires with a questID on this build.
- How chatty `ZONE_CHANGED` subzone transitions are in starting zones (debounce is 1.5 s).
- Whether the per-character SV file lands under `WTF/Account/<acct>/70/Rambleon-Birdsong/SavedVariables/`.
- Whether `QuestBG-Parchment` atlas exists (harmless either way) and how the panel looks.
- Any events listed under "failed events" in `/ramble debug`.

### Later
- Milestone 2: nicer timeline, satisfying MARK MOMENT, minimap button or keybind polish, Tier 2 events (loot, hearth).
- Milestone 3: chapter numbering across many sessions, recap cards, weekly recap.
