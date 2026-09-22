# Rambleon

**Your Azeroth Adventure Journal.** Play World of Warcraft: Forever normally. Rambleon quietly remembers the
adventure. When the night ends, it hands you a permanent record: a timeline, a factual log, and (optionally) an
AI-written chapter based only on what actually happened.

```
Rambleon Birdsong
September 21, 2026
2h 14m in Azeroth

8:17 PM — Entered Dolanaar
8:24 PM — Accepted "The Emerald Dreamcatcher"
8:41 PM — Reached Level 12
8:53 PM — Died in Fel Rock
9:04 PM — Joined forces with Moonhoof
```

Two parts:

1. **The AddOn** (`addon/Rambleon`) listens for game events, keeps the current session in memory, shows a small
   parchment panel (`/ramble`), lets you mark moments and write notes, and hands the session to WoW's SavedVariables.
2. **The Mac companion** (`companion/`, command `ramble`) watches the SavedVariables file, snapshots every write into an
   immutable archive, converts it to JSON, and produces Markdown reports and AI journal prompts.

The archive on the Mac is the source of truth. This matters because the current Forever beta does not restore AddOn
SavedVariables on the next launch (see `docs/addon-api.md`). WoW may forget; Rambleon does not.

## Setup

```bash
scripts/bootstrap        # installs uv, the companion env, and the global `ramble` command
ramble doctor            # WoW Forever: FOUND / Rambleon AddOn: INSTALLED / Archive: READY ...
ramble install           # symlinks addon/Rambleon into the Forever AddOns folder
```

## A night in Azeroth

```bash
ramble watch             # leave running in a terminal while you play
```

In game: `/ramble` opens the log. Play. `/ramble note this cave is extremely cursed`. `/ramble mark`.
When you are done, just log out. WoW writes the log to disk on logout (and on every `/reload`); the watcher prints
`captured …`, waits ten minutes in case you come back, and then writes the night's chapter. Or, at any time:

```bash
ramble export tonight    # exports/markdown/2026-09-21-rambleon-birdsong.md (factual)
ramble summarize tonight # exports/prompts/... and, with the Claude CLI installed, the journal chapter + recap
```

**A chapter is a night in Azeroth.** Every session you played that evening (reloads, relogs, a break for dinner) is
stitched into one chapter. While `ramble watch` is running, finishing a night does all of this automatically: export,
journal (if the Claude CLI is logged in), an HTML story page with your screenshots in `exports/html/`, and a
`Chapters.lua` published into the AddOn. Next login, `/ramble chapters` shows the story with selectable text (Ctrl-A,
Ctrl-C) for pasting anywhere. `/ramble save` flushes the log to disk right now if you cannot wait for logout.

Also: `ramble sessions`, `ramble show latest`, `ramble status`, `ramble page latest` (opens the story page),
`ramble publish`, `ramble ingest` (one-shot capture if the watcher was not running), `ramble reprocess` (rebuild after upgrades).

## In-game commands

`/ramble` · `/ramble status` · `/ramble note <text>` · `/ramble mark` · `/ramble chapters` · `/ramble save` · `/ramble debug [on|off]` · `/ramble dump`

Keybindings: "Open Adventure Log" and "Mark Moment" under AddOns in the Key Bindings menu.

## Principles

Passive. Never plays the game for you, never touches combat or protected information, never needs the network.
Records memories, not a combat log. AI interpretation is always downstream of the raw archive and never edits it.

## Development

```bash
scripts/test             # luac -p, simulated session under a WoW API stub, pytest
```

See `CLAUDE.md` for the philosophy and the dev loop, `docs/` for environment facts, API notes, the data model and progress.
