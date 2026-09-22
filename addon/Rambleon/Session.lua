-- Rambleon: the in-memory session and the RambleonDB SavedVariables shape.
-- Rule: every value stored under RambleonDB must be a string, number, boolean or table of those.
-- Rule: never trust that RambleonDB was restored (Forever beta bug). Every login may be a fresh table.
local ADDON, ns = ...

local RESUME_WINDOW = 600      -- seconds: resume a suspended session if it was seen this recently
local KEEP_SESSIONS = 10       -- non-active sessions kept in the SV table (the Mac archive owns history)
local HEARTBEAT = 30           -- seconds

ns.session = nil
ns.questTitles = {}
ns.currentGroup = {}           -- name -> { since = GetTime() }
ns.lastZoneKey = nil
ns.inInstance = nil
ns.isDead = false
ns.dbRestored = false
ns.dirty = false               -- UI refresh hint
ns.resumed = false
ns.lastXP, ns.lastXPMax = nil, nil
ns.doneObjectives = {}
ns.objectivesSeeded = false

function ns.InitDB()
  if type(RambleonDB) == "table" then
    ns.dbRestored = type(RambleonDB.sessions) == "table" and #RambleonDB.sessions > 0
  else
    RambleonDB = {}
  end
  RambleonDB.schemaVersion = ns.SCHEMA_VERSION
  RambleonDB.addonVersion = ns.VERSION
  if type(RambleonDB.sessions) ~= "table" then RambleonDB.sessions = {} end
end

-- Location ------------------------------------------------------------------

function ns.GetLocation()
  local loc = {}
  loc.zone = ns.CleanString(ns.SafeCall(GetRealZoneText)) or ns.CleanString(ns.SafeCall(GetZoneText))
  loc.subzone = ns.CleanString(ns.SafeCall(GetSubZoneText))
  if loc.subzone == loc.zone then loc.subzone = nil end
  if C_Map and C_Map.GetBestMapForUnit then
    loc.mapID = ns.Clean(ns.SafeCall(C_Map.GetBestMapForUnit, "player"))
  end
  local inInstance = ns.SafeCall(IsInInstance)
  if loc.mapID and not inInstance and C_Map.GetPlayerMapPosition then
    local pos = ns.SafeCall(C_Map.GetPlayerMapPosition, loc.mapID, "player")
    if pos and pos.GetXY then
      local x, y = ns.SafeCall(pos.GetXY, pos)
      x, y = ns.Clean(x), ns.Clean(y)
      if x and y then
        loc.x = math.floor(x * 1000 + 0.5) / 10   -- percent with one decimal
        loc.y = math.floor(y * 1000 + 0.5) / 10
      end
    end
  end
  return loc
end

-- Identity ------------------------------------------------------------------

function ns.CaptureCharacter()
  local c = {}
  c.name = ns.CleanString(ns.SafeCall(UnitName, "player"))
  if UnitFullName then
    local n, r = ns.SafeCall(UnitFullName, "player")
    c.fullName = ns.CleanString(n)
    c.realmFromFullName = ns.CleanString(r)
  end
  c.realm = ns.CleanString(ns.SafeCall(GetRealmName))
  c.normalizedRealm = ns.CleanString(ns.SafeCall(GetNormalizedRealmName))
  local race, raceFile = ns.SafeCall(UnitRace, "player")
  c.race, c.raceFile = ns.CleanString(race), ns.CleanString(raceFile)
  local class, classFile = ns.SafeCall(UnitClass, "player")
  c.class, c.classFile = ns.CleanString(class), ns.CleanString(classFile)
  c.faction = ns.CleanString(ns.SafeCall(UnitFactionGroup, "player"))
  c.guid = ns.CleanString(ns.SafeCall(UnitGUID, "player"))
  c.startLevel = ns.Clean(ns.SafeCall(UnitLevel, "player"))
  c.endLevel = c.startLevel
  return c
end

function ns.CaptureClient()
  local cl = {}
  local v, b, d, toc = ns.SafeCall(GetBuildInfo)
  cl.version, cl.build, cl.buildDate, cl.tocVersion = ns.Clean(v), ns.Clean(b), ns.Clean(d), ns.Clean(toc)
  cl.projectId = ns.Clean(WOW_PROJECT_ID)
  cl.flavorHint = ns.flavorHint
  cl.addonVersion = ns.VERSION
  cl.locale = ns.Clean(ns.SafeCall(GetLocale))
  if ns.flavorHint == "forever" then
    cl.flavor = "forever"
  elseif cl.tocVersion == 16001 then
    cl.flavor = "forever?"
  else
    cl.flavor = "unknown"
  end
  return cl
end

function ns.DisplayName()
  local c = ns.session and ns.session.character
  return (c and (c.fullName or c.name)) or ns.CleanString(ns.SafeCall(UnitName, "player")) or "Adventurer"
end

-- Session lifecycle ----------------------------------------------------------

local function newSessionId(character)
  local stamp = date("!%Y-%m-%dT%H%M%SZ")
  local base = stamp .. "_" .. ns.Slug(character.fullName or character.name or "unknown")
  local id, n = base, 1
  local taken = true
  while taken do
    taken = false
    for _, s in ipairs(RambleonDB.sessions) do
      if type(s) == "table" and s.id == id then taken = true break end
    end
    if taken then n = n + 1; id = base .. "-" .. n end
  end
  return id
end

local function findResumable(character)
  local now = ns.Now()
  for i = #RambleonDB.sessions, 1, -1 do
    local s = RambleonDB.sessions[i]
    if type(s) == "table" and s.state == "suspended" and s.character
       and s.character.name == character.name
       and type(s.lastSeen) == "number" and (now - s.lastSeen) <= RESUME_WINDOW then
      return s
    end
  end
  return nil
end

function ns.PruneSessions()
  local sessions = RambleonDB.sessions
  local nonActive = 0
  for _, s in ipairs(sessions) do
    if s.state ~= "active" then nonActive = nonActive + 1 end
  end
  local i = 1
  while nonActive > KEEP_SESSIONS and i <= #sessions do
    if sessions[i].state ~= "active" then
      table.remove(sessions, i)
      nonActive = nonActive - 1
    else
      i = i + 1
    end
  end
end

function ns.StartSession()
  local character = ns.CaptureCharacter()
  local resumed = findResumable(character)
  ns.playedAnchor = GetTime()
  ns.currentGroup = {}
  ns.resumed = false
  ns.doneObjectives = {}
  ns.objectivesSeeded = false
  if resumed then
    ns.session = resumed
    resumed.state = "active"
    resumed.resumes = (resumed.resumes or 0) + 1
    resumed.kills = resumed.kills or {}
    ns.resumed = true
    ns.AddEvent("RESUMED", {})
    ns.SeedFromSession()
    ns.Debug("resumed session " .. resumed.id)
    return resumed
  end
  local s = {
    id = newSessionId(character),
    schemaVersion = ns.SCHEMA_VERSION,
    state = "active",
    startedAt = ns.Now(),
    startedServerTime = ns.Clean(ns.SafeCall(GetServerTime)),
    lastSeen = ns.Now(),
    playedSeconds = 0,
    character = character,
    client = ns.CaptureClient(),
    counters = { levelsGained = 0, questsAccepted = 0, questsCompleted = 0, deaths = 0,
                 zonesVisited = 0, notes = 0, marks = 0, screenshots = 0, achievements = 0,
                 kills = 0, xpGained = 0, objectivesCompleted = 0, loot = 0 },
    zones = {},
    people = {},
    kills = {},                 -- name -> { count, xp, firstAt, lastAt }
    events = {},
    failedEvents = {},
  }
  for _, e in ipairs(ns.failedEvents) do table.insert(s.failedEvents, e) end
  table.insert(RambleonDB.sessions, s)
  ns.session = s
  ns.PruneSessions()
  ns.lastZoneKey = nil
  ns.AddEvent("SESSION_START", {})
  ns.Debug("new session " .. s.id)
  return s
end

-- After a resume, remember where we were and who we were with so nothing is logged twice.
function ns.SeedFromSession()
  local s = ns.session
  if not s then return end
  for i = #s.events, 1, -1 do
    local ev = s.events[i]
    if ev.type == "ZONE_ENTER" and ev.zone then
      ns.lastZoneKey = ev.zone .. "|" .. (ev.subzone or "")
      break
    end
  end
  ns.UpdateRoster(true)
end

-- Any recorder call goes through this: after END CHAPTER (without a reload) a new chapter starts.
function ns.EnsureSession()
  if not ns.session or ns.session.state ~= "active" then
    if not ns.loaded then return nil end
    ns.StartSession()
  end
  return ns.session
end

function ns.PlayedSeconds()
  local s = ns.session
  if not s then return 0 end
  local base = s.playedSeconds or 0
  if s.state == "active" and ns.playedAnchor then
    base = base + (GetTime() - ns.playedAnchor)
  end
  return base
end

local function flushPlaytime()
  local s = ns.session
  if not s or s.state ~= "active" or not ns.playedAnchor then return end
  local now = GetTime()
  s.playedSeconds = math.floor(((s.playedSeconds or 0) + (now - ns.playedAnchor)) + 0.5)
  ns.playedAnchor = now
  s.lastSeen = ns.Now()
end

function ns.FlushPeople()
  local s = ns.session
  if not s then return end
  local now = GetTime()
  for name, g in pairs(ns.currentGroup) do
    local p = ns.FindPerson(name)
    if p then
      p.seconds = math.floor((p.seconds or 0) + (now - g.since) + 0.5)
      p.lastSeen = ns.Now()
    end
    g.since = now
  end
end

function ns.Heartbeat()
  if not ns.session or ns.session.state ~= "active" then return end
  flushPlaytime()
  ns.FlushPeople()
  ns.dirty = true
end

function ns.EndSession(reason)
  local s = ns.session
  if not s or s.state ~= "active" then return nil end
  flushPlaytime()
  ns.FlushPeople()
  s.character.endLevel = ns.Clean(ns.SafeCall(UnitLevel, "player")) or s.character.endLevel
  ns.AddEvent("SESSION_END", { reason = reason or "end_chapter" })
  s.state = "ended"
  s.endedAt = ns.Now()
  s.endReason = reason or "end_chapter"
  ns.playedAnchor = nil
  ns.dirty = true
  return s
end

function ns.SuspendSession()
  local s = ns.session
  if not s or s.state ~= "active" then return end
  flushPlaytime()
  ns.FlushPeople()
  s.character.endLevel = ns.Clean(ns.SafeCall(UnitLevel, "player")) or s.character.endLevel
  s.state = "suspended"
  s.lastSeen = ns.Now()
  ns.playedAnchor = nil
end

-- Events ---------------------------------------------------------------------

local COUNTER_FOR = {
  LEVEL_UP = "levelsGained", QUEST_ACCEPTED = "questsAccepted", QUEST_COMPLETED = "questsCompleted",
  -- FIRST_KILL and OBJECTIVE_COMPLETE keep their own counters (kills, objectivesCompleted)
  DEATH = "deaths", NOTE = "notes", MARK = "marks", SCREENSHOT = "screenshots", ACHIEVEMENT = "achievements",
}

function ns.AddEvent(eventType, fields)
  local s = ns.session
  if not s then return nil end
  local ev = { t = ns.Now(), type = eventType }
  for k, v in pairs(fields or {}) do
    local clean = ns.Clean(v)
    if clean ~= nil then ev[k] = clean end
  end
  if ev.level == nil then ev.level = ns.Clean(ns.SafeCall(UnitLevel, "player")) end
  if ev.zone == nil and eventType ~= "ZONE_ENTER" and eventType ~= "SESSION_START" then
    local loc = ns.GetLocation()
    ev.zone, ev.subzone = loc.zone, loc.subzone
  end
  table.insert(s.events, ev)
  local counter = COUNTER_FOR[eventType]
  if counter then s.counters[counter] = (s.counters[counter] or 0) + 1 end
  s.lastSeen = ev.t
  ns.dirty = true
  ns.Debug(eventType)
  return ev
end

-- Zones ----------------------------------------------------------------------

function ns.RecordZone(loc)
  local s = ns.session
  if not s or not loc.zone then return end
  local key = loc.zone .. "|" .. (loc.subzone or "")
  for _, z in ipairs(s.zones) do
    if (z.zone .. "|" .. (z.subzone or "")) == key then
      z.visits = (z.visits or 1) + 1
      z.lastSeen = ns.Now()
      return z
    end
  end
  local z = { zone = loc.zone, subzone = loc.subzone, mapID = loc.mapID,
              firstSeen = ns.Now(), lastSeen = ns.Now(), visits = 1 }
  table.insert(s.zones, z)
  s.counters.zonesVisited = #s.zones
  return z
end

function ns.NoteZoneChange(force)
  if not ns.EnsureSession() then return end
  local loc = ns.GetLocation()
  if not loc.zone then return end
  local key = loc.zone .. "|" .. (loc.subzone or "")
  if key == ns.lastZoneKey and not force then return end
  ns.lastZoneKey = key
  ns.RecordZone(loc)
  ns.AddEvent("ZONE_ENTER", { zone = loc.zone, subzone = loc.subzone, mapID = loc.mapID, x = loc.x, y = loc.y })
end

-- People ---------------------------------------------------------------------

function ns.FindPerson(name)
  local s = ns.session
  if not s then return nil end
  for _, p in ipairs(s.people) do
    if p.name == name then return p end
  end
  return nil
end

function ns.UpdateRoster(silent)
  local s = ns.EnsureSession()
  if not s then return end
  local present = {}
  local inGroup = ns.SafeCall(IsInGroup)
  if inGroup then
    local n = ns.SafeCall(GetNumGroupMembers) or 0
    local inRaid = ns.SafeCall(IsInRaid)
    for i = 1, n do
      local unit = (inRaid and "raid" or "party") .. i
      if ns.SafeCall(UnitExists, unit) and not ns.SafeCall(UnitIsUnit, unit, "player") then
        local name = ns.CleanString(ns.SafeCall(UnitName, unit))
        if name and name ~= UNKNOWNOBJECT then
          local class, classFile = ns.SafeCall(UnitClass, unit)
          present[name] = { class = ns.CleanString(class), classFile = ns.CleanString(classFile) }
        end
      end
    end
  end
  local now = GetTime()
  for name, info in pairs(present) do
    if not ns.currentGroup[name] then
      ns.currentGroup[name] = { since = now }
      local p = ns.FindPerson(name)
      if not p then
        p = { name = name, class = info.class, classFile = info.classFile,
              firstSeen = ns.Now(), lastSeen = ns.Now(), seconds = 0, joins = 0 }
        table.insert(s.people, p)
      end
      p.lastSeen = ns.Now()
      if not silent then
        p.joins = (p.joins or 0) + 1
        ns.AddEvent("GROUP_JOIN", { name = name, class = info.class })
      end
    end
  end
  for name, g in pairs(ns.currentGroup) do
    if not present[name] then
      local p = ns.FindPerson(name)
      if p then
        p.seconds = math.floor((p.seconds or 0) + (now - g.since) + 0.5)
        p.lastSeen = ns.Now()
      end
      ns.currentGroup[name] = nil
      ns.AddEvent("GROUP_LEAVE", { name = name })
    end
  end
end

-- Kills and experience --------------------------------------------------------
-- Source: the "X dies, you gain N experience." chat line. Only XP-granting kills are visible this way;
-- Rambleon never touches the combat log.

local xpPatterns
local function buildXpPatterns()
  if xpPatterns then return xpPatterns end
  xpPatterns = {}
  -- Client globals first (localised), English fallbacks after. Nil globals must not stop the loop.
  local formats = {}
  for _, fmt in pairs({ COMBATLOG_XPGAIN_FIRSTPERSON_GROUP, COMBATLOG_XPGAIN_FIRSTPERSON_RAID, COMBATLOG_XPGAIN_FIRSTPERSON }) do
    table.insert(formats, fmt)
  end
  table.insert(formats, "%s dies, you gain %d experience. (+%d group bonus)")
  table.insert(formats, "%s dies, you gain %d experience. (+%d raid bonus)")
  table.insert(formats, "%s dies, you gain %d experience.")
  local seen = {}
  for _, fmt in ipairs(formats) do
    if type(fmt) == "string" and not seen[fmt] then
      seen[fmt] = true
      local p = fmt:gsub("%%s", "\1"):gsub("%%d", "\2")
      p = p:gsub("[%(%)%.%%%+%-%*%?%[%]%^%$]", "%%%0")
      p = p:gsub("\1", "(.-)"):gsub("\2", "(%%d+)")
      table.insert(xpPatterns, "^" .. p .. "$")
    end
  end
  return xpPatterns
end

function ns.RecordKillFromChat(text)
  text = ns.CleanString(text)
  if not text then return end
  local s = ns.EnsureSession()
  if not s then return end
  local name, xp
  for _, pattern in ipairs(buildXpPatterns()) do
    name, xp = text:match(pattern)
    if name then break end
  end
  if not name or name == "" then return end
  xp = tonumber(xp) or 0
  s.kills = s.kills or {}
  local k = s.kills[name]
  if not k then
    k = { count = 0, xp = 0, firstAt = ns.Now(), lastAt = ns.Now() }
    s.kills[name] = k
    ns.AddEvent("FIRST_KILL", { name = name, xp = xp })
  end
  k.count = k.count + 1
  k.xp = k.xp + xp
  k.lastAt = ns.Now()
  s.counters.kills = (s.counters.kills or 0) + 1
  s.lastSeen = ns.Now()
  ns.dirty = true
end

function ns.SeedXP()
  ns.lastXP = ns.Clean(ns.SafeCall(UnitXP, "player"))
  ns.lastXPMax = ns.Clean(ns.SafeCall(UnitXPMax, "player"))
end

function ns.UpdateXP()
  local s = ns.session
  if not s or s.state ~= "active" then return end
  local xp = ns.Clean(ns.SafeCall(UnitXP, "player"))
  local max = ns.Clean(ns.SafeCall(UnitXPMax, "player"))
  if type(xp) ~= "number" then return end
  if type(ns.lastXP) == "number" then
    local delta
    if xp >= ns.lastXP then
      delta = xp - ns.lastXP
    else
      delta = ((ns.lastXPMax or 0) - ns.lastXP) + xp   -- levelled up in between
    end
    if delta > 0 then s.counters.xpGained = (s.counters.xpGained or 0) + delta end
  end
  ns.lastXP, ns.lastXPMax = xp, max
end

-- Quest objectives: "8/8 Timberling slain" finishing is a memory; each kill on the way is not.
function ns.ScanObjectives()
  local s = ns.session
  if not s or s.state ~= "active" then return end
  if not (C_QuestLog and C_QuestLog.GetNumQuestLogEntries and C_QuestLog.GetInfo and C_QuestLog.GetQuestObjectives) then return end
  local n = ns.SafeCall(C_QuestLog.GetNumQuestLogEntries) or 0
  for i = 1, n do
    local info = ns.SafeCall(C_QuestLog.GetInfo, i)
    if type(info) == "table" and not info.isHeader and type(info.questID) == "number" then
      local title = ns.CleanString(info.title)
      if title then ns.questTitles[info.questID] = title end
      local objectives = ns.SafeCall(C_QuestLog.GetQuestObjectives, info.questID)
      if type(objectives) == "table" then
        for idx, obj in ipairs(objectives) do
          if type(obj) == "table" and obj.finished then
            local key = info.questID .. "#" .. idx
            if not ns.doneObjectives[key] then
              ns.doneObjectives[key] = true
              if ns.objectivesSeeded then
                ns.AddEvent("OBJECTIVE_COMPLETE", { questID = info.questID, title = title, text = ns.CleanString(obj.text) })
                s.counters.objectivesCompleted = (s.counters.objectivesCompleted or 0) + 1
              end
            end
          end
        end
      end
    end
  end
  ns.objectivesSeeded = true
end

-- Loot worth remembering -----------------------------------------------------
-- Uncommon (green) or better items you receive or equip. Greys and whites are noise.

local MIN_QUALITY = 2
local QUALITY_NAMES = { [0] = "Poor", "Common", "Uncommon", "Rare", "Epic", "Legendary", "Artifact", "Heirloom" }
local LINK_COLORS = { ["1eff00"] = 2, ["0070dd"] = 3, ["a335ee"] = 4, ["ff8000"] = 5, ["e6cc80"] = 6, ["00ccff"] = 7 }

local function itemFromLink(link)
  if type(link) ~= "string" then return nil end
  local color, itemID, name = link:match("|c%x%x(%x%x%x%x%x%x)|Hitem:(%d+)[^|]*|h%[([^%]]*)%]|h")
  if not itemID then return nil end
  itemID = tonumber(itemID)
  local quality
  if C_Item and C_Item.GetItemQualityByID then
    quality = ns.Clean(ns.SafeCall(C_Item.GetItemQualityByID, itemID))
  end
  if type(quality) ~= "number" then quality = LINK_COLORS[color:lower()] or 1 end
  return { itemID = itemID, name = ns.CleanString(name), quality = quality }
end

local lootPatterns
local function buildLootPatterns()
  if lootPatterns then return lootPatterns end
  lootPatterns = {}
  local formats = {}
  for _, fmt in pairs({ LOOT_ITEM_SELF_MULTIPLE, LOOT_ITEM_PUSHED_SELF_MULTIPLE, LOOT_ITEM_CREATED_SELF_MULTIPLE,
                        LOOT_ITEM_SELF, LOOT_ITEM_PUSHED_SELF, LOOT_ITEM_CREATED_SELF }) do
    table.insert(formats, fmt)
  end
  for _, fmt in ipairs({ "You receive loot: %sx%d.", "You receive item: %sx%d.", "You create: %sx%d.",
                         "You receive loot: %s.", "You receive item: %s.", "You create: %s." }) do
    table.insert(formats, fmt)
  end
  local seen = {}
  for _, fmt in ipairs(formats) do
    if type(fmt) == "string" and not seen[fmt] then
      seen[fmt] = true
      local p = fmt:gsub("%%s", "\1"):gsub("%%d", "\2")
      p = p:gsub("[%(%)%.%%%+%-%*%?%[%]%^%$]", "%%%0")
      p = p:gsub("\1", "(.-)"):gsub("\2", "(%%d+)")
      table.insert(lootPatterns, "^" .. p .. "$")
    end
  end
  return lootPatterns
end

function ns.RecordLootFromChat(text)
  text = ns.CleanString(text)
  if not text then return end
  local link, count
  for _, pattern in ipairs(buildLootPatterns()) do
    link, count = text:match(pattern)
    if link then break end
  end
  if not link then return end
  local item = itemFromLink(link)
  if not item or item.quality < MIN_QUALITY then return end
  local s = ns.EnsureSession()
  if not s then return end
  ns.AddEvent("LOOT", { itemID = item.itemID, name = item.name, quality = item.quality,
                        qualityName = QUALITY_NAMES[item.quality], count = tonumber(count) or 1 })
  s.counters.loot = (s.counters.loot or 0) + 1
end

ns.equippedSeen = {}
function ns.RecordEquip(slot)
  if type(slot) ~= "number" or not GetInventoryItemLink then return end
  local link = ns.SafeCall(GetInventoryItemLink, "player", slot)
  local item = itemFromLink(link)
  if not item or item.quality < MIN_QUALITY then return end
  local s = ns.EnsureSession()
  if not s then return end
  local key = slot .. ":" .. item.itemID
  if ns.equippedSeen[key] then return end
  ns.equippedSeen[key] = true
  if not ns.equipSeeded then return end   -- the first pass after login just learns what is already worn
  ns.AddEvent("EQUIP", { itemID = item.itemID, name = item.name, quality = item.quality,
                         qualityName = QUALITY_NAMES[item.quality], slot = slot })
end

function ns.SeedEquipment()
  ns.equipSeeded = false
  for slot = 1, 19 do ns.RecordEquip(slot) end
  ns.equipSeeded = true
end

-- Manual moments -------------------------------------------------------------

function ns.AddNote(text)
  text = ns.Trim(text)
  if text == "" then return nil end
  if not ns.EnsureSession() then return nil end
  if #text > 500 then text = text:sub(1, 500) end
  return ns.AddEvent("NOTE", { text = text })
end

function ns.MarkMoment()
  if not ns.EnsureSession() then return nil end
  return ns.AddEvent("MARK", {})
end

-- Heartbeat ticker (started once the world is entered)
function ns.StartHeartbeat()
  if ns.heartbeatTicker then return end
  if C_Timer and C_Timer.NewTicker then
    ns.heartbeatTicker = C_Timer.NewTicker(HEARTBEAT, ns.Heartbeat)
  end
end
