# AddOn API notes for World of Warcraft: Forever

Researched 2026-09-21. Sources are listed at the end. Anything marked *verify in-game* is unconfirmed on our client.

## What Forever is, for an AddOn author

- Forever (codename **Camelot**) runs the **mainline 12.x UI codebase** ("all Modern changes up to 12.0.7" per
  warcraft.wiki.gg; Blizzard devs cite the 12.1.5 API surface) while reporting version **1.60.1**.
  It is distributed as product `wow_classic_beta`, so it lives in `_classic_beta_`, but it is not a Classic client.
- Beta: Sept 17 – Oct 21, 2026. Level cap 20, rising to 30 later.
- `GetBuildInfo()` on build 69913 returns `"1.60.1", "69913", "Sep 17 2026", 16001`.

## TOC and flavor detection

| Item | Value |
|---|---|
| `## Interface:` | `16001` |
| Flavor TOC suffix | `Rambleon_Camelot.toc` (also matched by `_Mainline`); we ship a plain `Rambleon.toc` fallback too |
| `WOW_PROJECT_ID` | `1` (`WOW_PROJECT_MAINLINE`). There is **no** Forever constant. |
| Our detection | `Forever.lua` is listed only in the Camelot TOC and sets `ns.flavorHint = "forever"`; `tocVersion == 16001` is the secondary hint |
| Game mode | `C_GameRules.GetActiveGameMode()` exists but its numbering does not match `currentGameMode "15"` in Config.wtf. Not used. |

## What is gone or restricted

- `GetSpecialization*` do not exist. Legacy globals `GetItemInfo`, `GetSpellInfo`, `UnitAura` moved to `C_*` namespaces.
- `COMBAT_LOG_EVENT` / `COMBAT_LOG_EVENT_UNFILTERED` error on registration. We never register them.
- **`RegisterEvent` throws on unknown events.** Every registration in `Events.lua` goes through `ns.SafeRegister`
  (pcall); failures are listed in `/ramble debug` and stored in the session as `failedEvents`.
- Lua error reporting stops after 100 errors per session. Keep the addon error-free; `pcall` anything uncertain.
- **Secret values (12.0):** unit health/power/auras/cooldowns/cast/threat and, in some encounter contexts, unit identity.
  Zone text, quest titles, level and map position are not restricted. `ns.Clean()` refuses secret values before
  anything reaches SavedVariables (a secret value in SV would be an error).
- `C_Map.GetPlayerMapPosition` returns nil inside instances. We record coordinates only when they are available.
- `C_UI.Reload()` is hardware-event restricted on retail. One Forever report says it is fully protected there.
  END & SAVE calls it inside `pcall` from the popup button; if the UI is still up one second later the panel says
  "Type /reload to save this chapter." *Verify in-game.*

## Names and realms

Forever has surnames and no realms. Reports: `UnitFullName("player")` → `"Rambleon Birdsong", "Classic Beta PvE"`;
`GetNormalizedRealmName()` may be nil or empty. The WTF folder is `70/Rambleon-Birdsong`. Rambleon stores the raw
results of `UnitName`, `UnitFullName`, `GetRealmName` and `GetNormalizedRealmName` and never splits on `-`.
*Verify in-game what each returns.*

## Events Rambleon uses

| Event | Used for | Notes |
|---|---|---|
| `ADDON_LOADED` | init `RambleonDB` | if nil (the beta bug), a fresh table is created; nothing is migrated |
| `PLAYER_LOGIN` | one chat line | |
| `PLAYER_ENTERING_WORLD` | start/resume the session, first zone, instance check, roster | |
| `PLAYER_LOGOUT` | suspend the session | fires before SV are written, on logout and `/reload` |
| `ZONE_CHANGED_NEW_AREA`, `ZONE_CHANGED`, `ZONE_CHANGED_INDOORS` | `ZONE_ENTER` | debounced 1.5 s; only logged when (zone, subzone) actually changes |
| `PLAYER_LEVEL_UP` | `LEVEL_UP` | arg1 = new level |
| `QUEST_ACCEPTED` | `QUEST_ACCEPTED` | retail passes `(questID)`, classic `(index, questID)`; both handled. Title from `C_QuestLog.GetTitleForQuestID`, retried once after 1 s |
| `QUEST_TURNED_IN` | `QUEST_COMPLETED` | `(questID, xp, money)` |
| `PLAYER_DEAD` / `PLAYER_UNGHOST` / `PLAYER_ALIVE` | `DEATH` / `REVIVED` | revival only logged if `UnitIsDeadOrGhost` is false |
| `GROUP_ROSTER_UPDATE` | `GROUP_JOIN` / `GROUP_LEAVE`, people table | roster diff, names guarded against secret values, time together accumulated on heartbeat |
| `UPDATE_INSTANCE_INFO` | `INSTANCE_ENTER` / `INSTANCE_EXIT` | via `IsInInstance()` transitions |
| `ACHIEVEMENT_EARNED` | `ACHIEVEMENT` | pcall-registered; may not exist |
| `SCREENSHOT_SUCCEEDED` | `SCREENSHOT` | no payload; the companion pairs the file by time |

Deliberately not recorded in v0.1: XP ticks, loot, bag/equipment changes, chat, anything from combat.

## SavedVariables mechanics and the Forever beta bug

**Mechanics (warcraft.wiki.gg):** SV are written on logout, `/reload`, disconnect and quit; not on crash. Only strings,
numbers, booleans and tables persist. Load order: FrameXML → addon code → SV load → `ADDON_LOADED(name)` → `PLAYER_LOGIN`.
`PLAYER_LOGOUT` fires just before SV are written, so changes made there persist.

**The bug (build 1.60.1.69913, since ~2026-09-17):** the client writes `<AddOn>.lua` correctly but never opens it on the
next load. Globals are nil at `ADDON_LOADED`. It affects both `SavedVariables` and `SavedVariablesPerCharacter`, on cold
start, logout/login and (for most people) `/reload`. It reproduces with no addons installed (default Blizzard frames
lose their positions too). There is no Blizzard response. One "works after the reset" post on 09-21 is contradicted by
"no fix yet" the same day. Treat it as **not fixed**.

Consequences and our design:

1. Every login is a new session unless a `suspended` session for the same character was seen < 10 minutes ago
   (works whether or not the DB was restored).
2. WoW overwrites the file with the current in-memory table at every flush, so after a fresh login the file only
   contains the current session. The Mac watcher snapshots every write and merges by session id; an archived session
   is never shrunk or deleted by a later, smaller file.
3. We do **not** use the community workarounds (ForeverSVFix, WTFix) that load SV through the addon-file loader.
4. A crash loses the in-memory session. END CHAPTER (or `/reload`) is what makes it permanent.

## Sources

- https://warcraft.wiki.gg/wiki/TOC_format · https://warcraft.wiki.gg/wiki/WOW_PROJECT_ID · https://warcraft.wiki.gg/wiki/API_GetBuildInfo
- https://warcraft.wiki.gg/wiki/Secret_values · https://warcraft.wiki.gg/wiki/Patch_12.0.0/API_changes
- https://warcraft.wiki.gg/wiki/SavedVariables · https://warcraft.wiki.gg/wiki/Saving_variables_between_game_sessions
- https://warcraft.wiki.gg/wiki/PLAYER_LOGOUT · https://warcraft.wiki.gg/wiki/API_C_UI.Reload · https://warcraft.wiki.gg/wiki/API_C_Map.GetPlayerMapPosition
- https://us.forums.blizzard.com/en/wow/t/wowf-beta-addon-savedvariables-appear-to-write-correctly-to-disk-but-are-not-restored-at-startup/2356559
- https://us.forums.blizzard.com/en/wow/t/uiaddon-settings-wiped-on-client-restart/2353992
- https://us.forums.blizzard.com/en/wow/t/savedvariables-never-load-in-the-beta-%E2%80%94-all-addon-settings-reset-on-login-69913/2354798
- https://eu.forums.blizzard.com/en/wow/t/forever-beta-160169913-savedvariables-fail-to-load-on-client-startupreload-%E2%80%94-all-addon-settings-reset-on-restart/629888
- https://github.com/ClassicWoWCommunity/forever-bugs/issues/34 · https://github.com/nobewayo/ForeverSVFix
- https://github.com/Cidan/BetterBags/pull/1092 · https://github.com/Total-RP/Total-RP-3/pull/1367 · https://github.com/wowaddonmaker/classicuiforever/issues/13
- https://news.blizzard.com/en-us/article/24304160/the-world-of-warcraft-forever-beta-now-live
