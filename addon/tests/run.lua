-- Offline smoke test: load Rambleon under the stub, play a scripted session, check the DB is SV-safe,
-- and write a Blizzard-format fixture for the companion's parser tests.
local here = arg[0]:match("^(.*)/[^/]*$") or "."
local addonDir = here .. "/../Rambleon"
local WoW = dofile(here .. "/wowstub.lua")

local ns = {}
local files = { "Forever.lua", "Util.lua", "Core.lua", "Session.lua", "Journal.lua", "Events.lua", "UI.lua", "Commands.lua" }
for _, f in ipairs(files) do
  local chunk, err = loadfile(addonDir .. "/" .. f)
  assert(chunk, err)
  chunk("Rambleon", ns)
end

local function assertEq(a, b, msg) if a ~= b then error((msg or "") .. ": expected " .. tostring(b) .. " got " .. tostring(a), 2) end end

-- Boot
WoW.Fire("ADDON_LOADED", "Rambleon")
WoW.Fire("PLAYER_LOGIN")
WoW.Fire("PLAYER_ENTERING_WORLD", true, false)
WoW.Advance(2)                                   -- zone debounce fires
assert(ns.session, "session should exist")
assertEq(ns.session.state, "active", "state")
assertEq(ns.session.character.fullName, "Rambleon Birdsong", "fullName")
assertEq(ns.session.client.flavor, "forever", "flavor")
assertEq(ns.session.events[1].type, "SESSION_START", "first event")
assertEq(ns.session.events[2].type, "ZONE_ENTER", "second event")
assertEq(ns.session.events[2].subzone, "Shadowglen", "subzone")

-- Zone spam: same place twice must not add events
WoW.Fire("ZONE_CHANGED"); WoW.Fire("ZONE_CHANGED_INDOORS"); WoW.Advance(2)
assertEq(#ns.session.events, 2, "no duplicate zone event")

-- Travel
WoW.state.subzone = "Dolanaar"; WoW.Fire("ZONE_CHANGED_NEW_AREA"); WoW.Advance(2)
assertEq(ns.session.events[#ns.session.events].subzone, "Dolanaar", "moved to Dolanaar")
assertEq(#ns.session.zones, 2, "two zones")

-- Quests
WoW.Fire("QUEST_ACCEPTED", 123)
WoW.Fire("QUEST_ACCEPTED", 5, 124)              -- classic-style args
WoW.Fire("QUEST_TURNED_IN", 123, 450, 0)
assertEq(ns.session.counters.questsAccepted, 2, "accepted")
assertEq(ns.session.counters.questsCompleted, 1, "completed")
assertEq(ns.session.events[#ns.session.events].title, "The Emerald Dreamcatcher", "title")

-- Level
WoW.state.level = 11; WoW.Fire("PLAYER_LEVEL_UP", 11)
assertEq(ns.session.character.endLevel, 11, "endLevel")

-- Death and revival
WoW.state.dead = true; WoW.Fire("PLAYER_DEAD")
WoW.state.dead = false; WoW.Fire("PLAYER_UNGHOST")
assertEq(ns.session.counters.deaths, 1, "deaths")
assertEq(ns.session.events[#ns.session.events].type, "REVIVED", "revived")

-- People
WoW.state.group.party1 = { name = "Moonhoof", class = "Druid" }
WoW.Fire("GROUP_ROSTER_UPDATE")
WoW.Advance(90)                                  -- heartbeats tick
WoW.Fire("GROUP_ROSTER_UPDATE")                  -- no change → no event
WoW.state.group.party1 = nil
WoW.Fire("GROUP_ROSTER_UPDATE")
assertEq(#ns.session.people, 1, "one person")
assert(ns.session.people[1].seconds >= 89, "grouped seconds ~90, got " .. tostring(ns.session.people[1].seconds))
local joins, leaves = 0, 0
for _, ev in ipairs(ns.session.events) do
  if ev.type == "GROUP_JOIN" then joins = joins + 1 elseif ev.type == "GROUP_LEAVE" then leaves = leaves + 1 end
end
assertEq(joins, 1, "joins"); assertEq(leaves, 1, "leaves")

-- Manual moments via slash commands
ns.HandleSlash("note this cave is extremely cursed")
ns.HandleSlash("mark")
ns.HandleSlash("status")
ns.HandleSlash("")                               -- toggles panel (builds UI)
assert(RambleonPanel:IsShown(), "panel shown")
ns.UI.Refresh()
ns.HandleSlash("debug")
assertEq(ns.session.counters.notes, 1, "notes")
assertEq(ns.session.counters.marks, 1, "marks")

-- Kills via the XP chat line (no combat log)
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "Timberling dies, you gain 45 experience.")
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "Timberling dies, you gain 45 experience. (+9 group bonus)")
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "Grell dies, you gain 50 experience.")
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "You gain 200 experience.")   -- not a kill
assertEq(ns.session.counters.kills, 3, "kills")
assertEq(ns.session.kills["Timberling"].count, 2, "timberling count")
assertEq(ns.session.kills["Timberling"].xp, 90, "timberling xp")
local firstKills = 0
for _, ev in ipairs(ns.session.events) do if ev.type == "FIRST_KILL" then firstKills = firstKills + 1 end end
assertEq(firstKills, 2, "first kills")

-- XP accounting across a level-up
WoW.state.xp, WoW.state.xpMax = 950, 1000; WoW.Fire("PLAYER_XP_UPDATE", "player")
WoW.state.level = 12; WoW.state.xp, WoW.state.xpMax = 100, 1200; WoW.Fire("PLAYER_LEVEL_UP", 12)
assertEq(ns.session.counters.xpGained, 50 + 50 + 100, "xp gained")

-- Quest objectives: first scan seeds silently, later completions are events
WoW.state.questLog = { { questID = 124, title = "Precious Waters", objectives = { { text = "0/8 Timberling slain", finished = false } } } }
WoW.Fire("UNIT_QUEST_LOG_CHANGED", "player"); WoW.Advance(2)
WoW.state.questLog[1].objectives[1] = { text = "8/8 Timberling slain", finished = true }
WoW.Fire("UNIT_QUEST_LOG_CHANGED", "player"); WoW.Advance(2)
WoW.Fire("QUEST_LOG_UPDATE"); WoW.Advance(2)
assertEq(ns.session.counters.objectivesCompleted, 1, "objective completed once")
assertEq(ns.session.events[#ns.session.events].type, "OBJECTIVE_COMPLETE", "objective event")

-- Screenshot + achievement + instance
WoW.Fire("SCREENSHOT_SUCCEEDED")
WoW.Fire("ACHIEVEMENT_EARNED", 6)
WoW.state.inInstance = true; WoW.state.instanceType = "party"; WoW.state.instanceName = "Ragefire Chasm"
WoW.Fire("UPDATE_INSTANCE_INFO")
WoW.state.inInstance = false; WoW.state.instanceType = "none"
WoW.Fire("UPDATE_INSTANCE_INFO")

-- End chapter through the UI path
WoW.Advance(300)
ns.UI.PromptEndChapter()
assertEq(WoW.lastPopup, "RAMBLEON_END", "end popup")
StaticPopupDialogs.RAMBLEON_END.OnAccept()
assertEq(ns.session.state, "ended", "ended")
assert(WoW.reloadCalled, "reload attempted")
assert(ns.session.playedSeconds >= 390, "played seconds")
local ended = ns.session

-- A /reload with a restored DB resumes the session without duplicating the roster or zone
do
  local saved = ns.session
  ns.session = nil
  ns.enteredWorld = false
  ns.lastZoneKey = nil
  ns.currentGroup = {}
  saved.state = "suspended"; saved.lastSeen = ns.Now()
  WoW.state.group.party1 = { name = "Moonhoof", class = "Druid" }
  WoW.state.subzone = "Dolanaar"
  local before = #saved.events
  WoW.Fire("PLAYER_ENTERING_WORLD", false, true); WoW.Advance(2)
  assert(ns.session == saved, "resumed the suspended session")
  assertEq(ns.session.events[before + 1].type, "RESUMED", "resumed event")
  assertEq(#ns.session.events, before + 1, "no duplicate join/zone after resume")
  WoW.state.group.party1 = nil
  WoW.Fire("GROUP_ROSTER_UPDATE")
  assertEq(ns.session.events[#ns.session.events].type, "GROUP_LEAVE", "leave still detected after resume")
  ns.UI.EndChapterAndReload()
end

-- Marking after an ended chapter starts a fresh chapter automatically
ns.HandleSlash("mark")
assert(ns.session ~= ended, "new session after end")
assertEq(#RambleonDB.sessions, 2, "two sessions in DB")
assert(RambleonDB.sessions[1].id ~= RambleonDB.sessions[2].id, "session ids must differ")

-- Logout suspends
WoW.Fire("PLAYER_LOGOUT")
assertEq(ns.session.state, "suspended", "suspended")

-- SavedVariables safety: only string/number/boolean/table, no NaN
local function check(v, path)
  local t = type(v)
  if t == "table" then
    for k, x in pairs(v) do
      assert(type(k) == "string" or type(k) == "number", "bad key at " .. path)
      check(x, path .. "." .. tostring(k))
    end
  elseif t == "number" then
    assert(v == v, "NaN at " .. path)
  else
    assert(t == "string" or t == "boolean", "bad type " .. t .. " at " .. path)
  end
end
check(RambleonDB, "RambleonDB")
assertEq(#ns.failedEvents, 0, "no failed registrations in stub")

-- Write the fixture
local fixtureDir = here .. "/../../companion/tests/fixtures"
local text = WoW.SerializeSavedVariables({ "RambleonDB" })
local fh = assert(io.open(fixtureDir .. "/Rambleon_simulated.lua", "wb"))
fh:write(text); fh:close()
print(string.format("OK — %d sessions, %d events in session 1, fixture written (%d bytes)",
  #RambleonDB.sessions, #ended.events, #text))
