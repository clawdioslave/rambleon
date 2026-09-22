# Data model

## 1. What the AddOn writes (`RambleonDB`, schemaVersion 1)

`## SavedVariablesPerCharacter: RambleonDB`, so WoW writes
`WTF/Account/<ACCOUNT>/<realm folder>/<Character-Name>/SavedVariables/Rambleon.lua`.

Only strings, numbers, booleans and tables are ever stored (`ns.Clean` enforces this and refuses secret values).

```lua
RambleonDB = {
  schemaVersion = 1,
  addonVersion = "0.1.0",
  sessions = {                     -- array, oldest first; at most 10 non-active sessions are kept in WoW
    {
      id = "2026-09-21T201547Z_rambleon-birdsong",
      schemaVersion = 1,
      state = "active" | "suspended" | "ended",
      startedAt = 1790000000,      -- epoch seconds, time()
      startedServerTime = ...,     -- GetServerTime(), for cross-checking clocks
      lastSeen = ...,              -- bumped every event and every 30 s heartbeat
      endedAt = ..., endReason = "end_chapter" | ...,
      playedSeconds = 8040,
      resumes = 0,
      character = { name, fullName, realmFromFullName, realm, normalizedRealm, race, raceFile, class, classFile,
                    faction, guid, startLevel, endLevel },
      client = { version, build, buildDate, tocVersion, projectId, flavorHint, flavor, addonVersion, locale },
      counters = { levelsGained, questsAccepted, questsCompleted, deaths, zonesVisited, notes, marks, screenshots, achievements,
                   kills, xpGained, objectivesCompleted, loot },
      zones = { { zone, subzone, mapID, firstSeen, lastSeen, visits }, ... },
      people = { { name, class, classFile, firstSeen, lastSeen, seconds, joins }, ... },
      kills = { ["Timberling"] = { count = 12, xp = 540, firstAt = ..., lastAt = ... }, ... },
      events = { { t = 1790000123, type = "ZONE_ENTER", zone = "Teldrassil", subzone = "Dolanaar", mapID = 57, x = 55.3, y = 58.1, level = 11 }, ... },
      failedEvents = { "ACHIEVEMENT_EARNED" },   -- registrations the client refused
    },
  },
}
```

### Event types

| type | fields |
|---|---|
| `SESSION_START`, `RESUMED`, `SESSION_END {reason}` | |
| `ZONE_ENTER` | `zone`, `subzone`, `mapID`, `x`, `y` (map percent, one decimal; absent in instances) |
| `LEVEL_UP` | `level` |
| `QUEST_ACCEPTED`, `QUEST_COMPLETED` | `questID`, `title` (+ `xp`, `money` on completion) |
| `DEATH`, `REVIVED` | |
| `GROUP_JOIN {name, class}`, `GROUP_LEAVE {name}` | |
| `INSTANCE_ENTER {name, instanceType}`, `INSTANCE_EXIT` | |
| `ACHIEVEMENT {id, name}` | |
| `SCREENSHOT` | timestamp only; the companion finds the file |
| `NOTE {text}`, `MARK` | |
| `FIRST_KILL {name, xp}` | first time an enemy of that name gave XP this session (from the "X dies, you gain N experience." chat line; no combat log) |
| `OBJECTIVE_COMPLETE {questID, title, text}` | a quest objective finished, e.g. "8/8 Timberling slain" |
| `LOOT {itemID, name, quality, qualityName, count}` | an uncommon-or-better item you received (loot, quest reward, crafted); from the chat loot line |
| `EQUIP {itemID, name, quality, qualityName, slot}` | an uncommon-or-better item equipped, once per item per session |

Every event also carries `level`, and `zone`/`subzone` unless it is a zone event itself.

### States

- `active` while playing. `PLAYER_LOGOUT` (logout and `/reload`) turns it into `suspended`.
- END CHAPTER turns it into `ended`. Recording anything afterwards starts a new session automatically.
- On load, a `suspended` session for the same character seen < 10 minutes ago is resumed (`RESUMED` event).

## 2. The Lua subset the companion parses

`companion/src/rambleon/luaparse.py` is a hand-written tokenizer + recursive-descent parser. It never executes Lua.
It accepts what Blizzard's serializer emits (observed on this machine, see `environment.md`) plus a little slack:

- `Name = value` assignments at top level, repeated; `nil` allowed as a top-level value.
- Tables `{ ... }` with `["key"] = v`, `[123] = v`, bare positional values (1-based; a positional `nil,` advances the
  index without storing), and `key = v` for hand-edited files. Trailing `,` or `;` after every entry.
- Strings with `\"`, `\\`, `\n`, `\r`, `\t`, `\a`, `\b`, `\f`, `\v`, `\ddd`, `\xhh`, backslash-newline. `|` is not escaped.
- Numbers: integers, floats (`%.16g` output), exponents, hex; plus non-Lua spellings `inf`, `-inf`, `nan`, `-nan(ind)`,
  `1.#INF`, `1.#IND`, `1.#QNAN` (Windows clients) mapped to IEEE values.
- `-- comments` and `--[[ ]]` blocks. CRLF and a leading blank line.
- Guards: 64 MB size cap, 500 levels of nesting. An unexpected end of file raises `TornFile` (WoW was still writing);
  any other problem raises `LuaParseError`.

`to_python()` turns tables keyed exactly `1..n` into lists and everything else into string-keyed dicts.

## 3. Normalized session JSON (`archive/sessions/normalized/<YYYY-MM-DD_HHMM>_<slug>.json`)

```json
{
  "schemaVersion": 1, "normalizedVersion": 1,
  "id": "2026-09-21T201547Z_rambleon-birdsong",
  "addonState": "ended", "state": "ended",
  "startedAt": 1790000000, "startedServerTime": 1790000001, "endedAt": 1790008040, "lastSeen": 1790008040,
  "playedSeconds": 8040, "endReason": "end_chapter", "resumes": 0,
  "character": { "...raw fields...", "displayName": "Rambleon Birdsong", "slug": "rambleon-birdsong" },
  "client": { "...": "..." },
  "counters": { "levelsGained": 2, "...": 0 },
  "events": [ { "t": 1790000123, "type": "ZONE_ENTER", "zone": "Teldrassil", "subzone": "Dolanaar", "mapID": 57 } ],
  "zones": [], "people": [], "failedEvents": [],
  "screenshots": [ { "path": "...", "file": "WoWScrnShot_092126_201547.jpg", "takenAt": 1790000500, "nearestEventIndex": 4, "nearestEventSeconds": 12 } ],
  "archive": { "capturedAt": 1790008100, "rawSnapshot": "sessions/raw/2026-09-22T031500Z_ab12cd34_Rambleon.lua",
               "sourceHash": "...", "sourceFile": ".../WTF/Account/<ACCOUNT>/70/Rambleon-Birdsong/SavedVariables/Rambleon.lua",
               "firstCapturedAt": 1790008100, "revision": 1 }
}
```

Normalization rules:
- Timestamps stay epoch seconds (UTC). Only exports render local time.
- `state` is the *effective* state: a `suspended`/`active` session whose `lastSeen` is more than 10 minutes old is
  reported as `ended` with `endedAt = lastSeen` and `endReason = "logout"`. `addonState` keeps the original.
- Events are sorted by `t` (stable). Non-scalar event fields are dropped.
- A session without an id, start time, character or event list is skipped.

## 4. Archive rules (`archive/`)

```
archive/
  sessions/raw/            <utc stamp>_<hash8>_Rambleon.lua   exact bytes WoW wrote; never modified
  sessions/raw/hashes.json hash → raw file (dedupe)
  sessions/raw/failed/     files that would not parse, with a .reason.txt beside each
  sessions/normalized/     one JSON per session id
  sessions/normalized/history/  previous versions of any normalized file that was replaced
  screenshots/<session>/   only when `--copy-screenshots` is used (references are the default)
  index.json               rebuilt after every change
  watch.pid                present while `ramble watch` runs
```

- Raw snapshot first, always. Parsing happens after the bytes are safe.
- A normalized session is replaced only by a copy with **at least as many events** that is not a state downgrade
  (`ended` beats `suspended`). Fewer events → rejected and logged. Never deleted, never shrunk.
- A file whose `RambleonDB` has no sessions (the beta bug, or a fresh character) touches nothing.
- Atomic writes everywhere (`tmp` + `os.replace`).

## 5. Exports (`exports/`)

- `markdown/<date>-<slug>.md` — factual log (`ramble export`).
- `prompts/<date>-<slug>-prompt.md` — AI-neutral prompt with rules + evidence (`ramble summarize`).
- `markdown/<date>-<slug>-journal.md` and `social/<date>-<slug>-recap.txt` — when the Claude CLI wrote the chapter.

Generated artifacts are downstream of the archive and can always be regenerated. Raw history is never edited.
