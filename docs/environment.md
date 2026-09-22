# Environment

Inspected on 2026-09-21. Everything below was read from this Mac, not assumed.
Account identifiers are deliberately omitted; the companion discovers them at runtime with globs.

## Machine

| Item | Value |
|---|---|
| macOS | 26.0 (build 25A5346a) |
| CPU | arm64 (Apple Silicon) |
| Homebrew | 7.0.6 (`/opt/homebrew`) |
| Git | 2.52.0 (global identity configured) |
| Python | 3.11.8 via pyenv (`.python-version`); 3.13.2 also installed |
| uv | not installed at inspection time; installed by `scripts/bootstrap` via `brew install uv` |
| Lua | 5.5.1 (Homebrew) — used only for offline AddOn syntax checks and simulated sessions |
| node | present (unused) |
| Claude Code CLI | 2.1.181 at `~/.local/bin/claude`; non-interactive flags verified: `-p`, `--tools ""`, `--output-format json`, `--no-session-persistence`, `--bare`, `--model`, `--max-budget-usd` |
| fswatch / watchdog / lupa | not installed (not needed; the watcher polls) |

## World of Warcraft

| Item | Value |
|---|---|
| Battle.net | `/Applications/Battle.net.app` 2.52.12.17821 |
| WoW root | `/Applications/World of Warcraft/` |
| Installed flavors | **only** `_classic_beta_` (no `_retail_`, `_classic_`, `_classic_era_`) |
| Forever beta dir | `/Applications/World of Warcraft/_classic_beta_/` |
| Product flavor | `.flavor.info` → `wow_classic_beta`; `.build.info` → Product `wow_classic_beta`, Version **1.60.1.69913**, branch `us` |
| App bundle | `_classic_beta_/World of Warcraft Beta.app` (1.60.1 / 1.60.1.69913) |
| Renderer | Metal (`GxApi "MTL"`) |
| Locale | enUS |
| AddOns dir | `_classic_beta_/Interface/AddOns/` — existed, empty, writable by the user (no sudo) |
| WTF dir | `_classic_beta_/WTF/` |
| Account-wide SavedVariables | `_classic_beta_/WTF/Account/<ACCOUNT>/SavedVariables/<AddOn>.lua` |
| Per-character SavedVariables | `_classic_beta_/WTF/Account/<ACCOUNT>/70/Rambleon-Birdsong/SavedVariables/<AddOn>.lua` |
| Realm folder | numeric **`70`** (General.log shows `sourceRealm="70-1-2"`). An older folder `Classic Beta PvE/Rambleon/` exists containing only `AddOns.txt`. |
| Character folder | `Rambleon-Birdsong` — first name + surname (Forever has surnames and no realms) |
| Screenshots dir | `_classic_beta_/Screenshots/` — does **not** exist yet; WoW creates it on the first screenshot. Filenames are `WoWScrnShot_MMDDYY_HHMMSS.<jpg|png|tga>` in local time. |
| Logs / Errors | `_classic_beta_/Logs/`, `_classic_beta_/Errors/` (three SIGTERM hang reports from 09-19) |
| Existing AddOns | none |
| Config.wtf hints | `engineSurveyPatch "16001"`, `currentGameMode "15"` |

### Blizzard SavedVariables seen on disk

Per-character: `Blizzard_DamageMeter`, `Blizzard_Communities`, `Blizzard_Professions`, `Blizzard_TimeManager`,
`Blizzard_RaidUI`, `Blizzard_LegacyChallengeTracker`, `Blizzard_SettingsDefinitions_Shared`, `Blizzard_ClientSavedVariables`.
Account-wide: `Blizzard_Console`, `Blizzard_PTRFeedback`, `Blizzard_SharedMapDataProviders`, `Blizzard_SavedSets`,
`Blizzard_GamepadSmartNavigation`. `Blizzard_DamageMeter` is a 12.0-era retail feature, which confirms Forever runs the
modern UI codebase despite the 1.60 version number.

### How WoW writes SavedVariables (observed)

- On flush WoW renames `X.lua` → `X.lua.bak` (overwriting the previous .bak) and then creates a brand-new `X.lua`
  (new inode every save). The write is **not atomic** — a reader can see a half-written file.
- Format: CRLF line endings, a leading blank line, **no indentation**, `["key"] = value`, `[3] = value`, bare
  positional entries, a trailing comma after every entry, `nil` written for empty globals, floats printed with
  `%.16g`, strings escaped with `\"`, `\n`, `\ddd`; the `|` character is not escaped.
- Flushes happen on logout, `/reload`, disconnect and quit. Not on crash.

## Rambleon paths (derived)

| Thing | Path |
|---|---|
| AddOn source | `<repo>/addon/Rambleon/` |
| Installed AddOn | `_classic_beta_/Interface/AddOns/Rambleon` → symlink to the source |
| Rambleon SavedVariables | `_classic_beta_/WTF/Account/*/*/*/SavedVariables/Rambleon.lua` (per-character) |
| Archive | `<repo>/archive/` (override with `RAMBLEON_ARCHIVE_DIR`) |
| WoW dir override | `RAMBLEON_WOW_DIR` (defaults to the Forever dir above) |
