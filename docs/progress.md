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

### Confirmed in game (2026-09-21, first session)
- Rambleon loads on Forever with Interface 16001; `/ramble` opens the panel; no event registration failed.
- `UnitName("player")` and `UnitFullName("player")` both return `"Rambleon Birdsong"`; realm `"Classic Beta PvE"`,
  normalized `"ClassicBetaPvE"`; `WOW_PROJECT_ID` 1; build 69913; GUID `Player-4618-…`; Dolanaar has mapID 1438.
- WoW wrote `Rambleon.lua` on `/reload`; `ramble watch` captured it within seconds and archived the session.
- **SavedVariables were restored across `/reload`** for this player (the session resumed: "Picked the story back up").
  Cold start behaviour still unknown.
- **`C_UI.Reload()` works from the END & SAVE button** on Forever (confirmed by the player).
- Bindings.xml must not use the `header` attribute, and must not be listed in the TOC at all (fixed).
- Group members and the zone were logged twice after a resume (fixed: the resume seeds roster and zone silently).
- Kills were invisible. Added kill tracking from the "X dies, you gain N experience." chat line, XP accounting,
  and quest objective completion events. The combat log stays untouched.

### Added after the first session
- `/ramble chapters`: an in-game reader for published chapters (journal or factual log + recap) with selectable text.
  The companion writes `addon/Rambleon/Chapters.lua`; WoW loads it as an addon file on `/reload`.
- `ramble page latest`: HTML story page (journal, recap, stats, screenshots, timeline) in `exports/html/` for Substack.
- `ramble watch` now runs export → journal → page → publish automatically when an ended chapter is captured.
- `ramble reprocess` rebuilds normalized sessions from raw snapshots after companion upgrades.

### Design change: running log, no END CHAPTER (player feedback)
- The END CHAPTER button is gone. The log just runs; logout writes it; `/ramble save` is an optional flush.
- A chapter is now a *night*: every session of an evening stitched together (`companion/src/rambleon/nights.py`).
  `ramble nights`, `ramble export tonight`, `ramble summarize tonight`, `ramble page tonight`.
- `ramble watch` finalizes a night ten minutes after the last write (the AddOn's resume window), or at once after
  `/ramble save`, then exports, journals, builds the page and publishes to the game.
- RESUMED markers are kept in the data but hidden from every rendered timeline.

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
