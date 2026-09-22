# Rambleon — where it goes next

Written 2026-09-21 after the first real night in Azeroth. This is a product plan, not a feature wishlist:
each phase has a reason, a "done" test, and the risks that could sink it.

## What we learned tonight

- The loop works end to end on the Forever beta: AddOn → SavedVariables → watcher → archive → Markdown → chapter in game.
- Players do not want to "end" anything. The log has to just run. Logging out is the save.
- The first thing the player asked for after seeing the log was the stuff that was missing: kills, then loot.
  The bar for "is this captured?" is the player's memory of the night, not an API list.
- Waiting is the enemy. "I couldn't wait and it's not there" will be every user's first complaint.
  Everything downstream of logout has to feel instant and obvious.
- The AddOn alone is not the product. The Mac side (archive, journal, story page) is where the value shows up.

## Product thesis

**Rambleon is a memory layer for World of Warcraft.** Strava for Azeroth. You play; it remembers; it hands you a
story you actually want to reread and share. The moat is not data capture (any addon can log events); it is the
archive over time and the quality of the retelling.

Who it is for: people who play a few nights a week and like their character as a character. Not raiders
optimising, not botters, not people who want a spreadsheet. The Substack/Discord/Bluesky sharer is the early adopter.

## Phase 1 — Make it dependable (next 1–2 weeks)

Goal: a friend can install it and never think about it again.

- [x] Background watcher via launchd (`ramble service install`): no terminal, starts at login.
- [x] Chapter written the moment you log out (WoW process / client log), with a macOS notification.
- [ ] `ramble doctor` becomes `ramble setup`: one command that installs the AddOn, the service, and opens the first page.
- [ ] Health: the watcher notices it is stale (the source changed underneath it) and restarts itself.
- [ ] Guard against the Battle.net updater deleting the AddOn symlink (doctor already reports it; auto-repair it).
- [ ] Cold-start verification of the SavedVariables bug on each new beta build; log which builds restore SV.
- [ ] Error reporting: `/ramble debug` output goes into the session so the Mac side can see client-side warnings.
- Done when: three consecutive nights produce a chapter with zero manual commands.

## Phase 2 — Make the chapter worth reading (2–4 weeks)

Goal: the AI chapter is good enough that the player pastes it somewhere without editing.

- [ ] Journal quality loop: keep every prompt + output; add a `ramble rate` (👍/👎 + note) so we can tune the rules.
- [ ] Chapter titles chosen from the night's events (already prompted); recap tuned to under 280 characters.
- [ ] Voice profiles: "field journal", "captain's log", "dry", "earnest". One prompt file each.
- [ ] Evidence density: the prompt gets zone descriptions and quest text pulled from the client's own data
  (`C_QuestLog.GetQuestInfo`, quest log text captured at accept time) so the AI has more true material.
- [ ] Screenshots on the timeline in game (a thumbnail is not possible; a marker + "1 screenshot here" is).
- [ ] Multiple AI backends behind the same adapter: Claude CLI (today), Claude API key, Ollama for fully local.
- Done when: the player shares a chapter unedited.

## Phase 3 — Memory over time (1–2 months)

Goal: answer "when did I first meet Moonhoof?" without a database.

- [ ] Character timeline page: every night, level curve, places, companions, deaths. A single HTML file.
- [ ] People page: who you have played with, how long, first met, last seen. From the archive index only.
- [ ] Weekly recap ("Week 3 in Azeroth") and season/arc grouping (levels 1–10, 10–20 …).
- [ ] Adventure map: plot ZONE_ENTER coordinates on the zone map images the client already ships (no bundling).
- [ ] Quest memory: "you did this quest on Sept 21 with Hazardelf".
- [ ] `ramble ask "..."`: an AI answer grounded in the archive (index + relevant nights as evidence).
- Done when: a 30-night archive answers the six questions in the original brief correctly.

## Phase 4 — Productize (when Phase 1–2 hold up)

Two halves, distributed separately, because that is how WoW players expect it:

**AddOn** (CurseForge / Wago / WoWUp):
- Ship `Rambleon` as a normal addon. Zero config. Works on Forever first; Retail and Classic are TOC work plus a
  test pass, since the code is already retail-12.x style.
- Without the companion it still gives the player the in-game log, notes, marks and the SavedVariables file.

**Companion** (Mac first):
- A small **menu-bar app** (SwiftUI or a Python + rumps shim to start) that wraps `ramble`: status dot, "last chapter",
  "open tonight's story", "open journal folder". No terminal. Signed and notarised.
- Later Windows: the same Python core with a tray icon; the WTF layout is identical.
- Distribution: Homebrew tap for the CLI now; a notarised .dmg for the app; a GitHub release per version.

**AI**:
- Default free path: paste the prompt anywhere (works today).
- Bring-your-own key (Claude/OpenAI-compatible) as an option; local Ollama as the privacy option.
- If it is ever hosted: the *only* thing that leaves the Mac is the prompt file, opt-in, per chapter.

**Privacy and rules** (the reason people will trust it):
- Passive only; never automates; never reads protected/secret values; never needs the network in game.
- The archive is plain JSON on the player's disk. Export everything, delete everything, one command each.
- Other players' names appear only as the game shows them (group roster). No chat content is stored.

**Business shape (not selling, but sustainable):**
- Free AddOn + free CLI, MIT. The menu-bar app is where a small one-time price or a "buy the author a coffee"
  could sit if it ever makes sense. No accounts, no subscription, no cloud unless the player asks for hosted AI.

## Risks

- **Forever beta churn.** Builds change weekly; the SavedVariables bug may vanish or mutate. The Mac archive design
  already survives either outcome; keep `docs/addon-api.md` current and re-verify on each build.
- **Blizzard addon policy.** Everything here is the normal UI API. The one thing to keep watching is Secret Values
  widening to zone/quest data; if that happens the journal degrades to notes + marks, which still works.
- **Symlink deletion by the updater.** Known Blizzard issue; `ramble install --copy` is the fallback.
- **AI cost/quality.** Keep the prompt-file path first-class so the product never depends on a paid API.
- **Scope creep.** The test for every feature stays: "will this help the player remember their adventure?"

## Next three things to build

1. `ramble setup` (AddOn + service + first page) so a new user needs one command.
2. Journal quality loop: rate chapters, tune the rules, add voice profiles.
3. The character timeline page.
