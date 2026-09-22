-- Rambleon: derived, human-readable views of the current session (UI, /ramble status, /ramble dump).
local ADDON, ns = ...
ns.Journal = {}
local J = ns.Journal

local function place(ev)
  return ev.subzone or ev.zone
end

function J.DescribeEvent(ev)
  local t = ev.type
  if t == "SESSION_START" then return "Began the adventure"
  elseif t == "RESUMED" then return "Picked the story back up"
  elseif t == "SESSION_END" then return "Ended the chapter"
  elseif t == "ZONE_ENTER" then
    if ev.subzone then return "Entered " .. ev.subzone .. " (" .. tostring(ev.zone) .. ")" end
    return "Entered " .. tostring(ev.zone)
  elseif t == "LEVEL_UP" then return "Reached Level " .. tostring(ev.level)
  elseif t == "QUEST_ACCEPTED" then return 'Accepted "' .. tostring(ev.title or ("quest " .. tostring(ev.questID))) .. '"'
  elseif t == "QUEST_COMPLETED" then return 'Completed "' .. tostring(ev.title or ("quest " .. tostring(ev.questID))) .. '"'
  elseif t == "DEATH" then return "Died in " .. tostring(place(ev) or "the wilds")
  elseif t == "REVIVED" then return "Back among the living"
  elseif t == "GROUP_JOIN" then return "Joined forces with " .. tostring(ev.name)
  elseif t == "GROUP_LEAVE" then return "Parted ways with " .. tostring(ev.name)
  elseif t == "INSTANCE_ENTER" then return "Entered " .. tostring(ev.name or "an instance")
  elseif t == "INSTANCE_EXIT" then return "Left " .. tostring(ev.name or "the instance")
  elseif t == "ACHIEVEMENT" then return "Achievement: " .. tostring(ev.name)
  elseif t == "SCREENSHOT" then return "Took a screenshot"
  elseif t == "NOTE" then return '"' .. tostring(ev.text) .. '"'
  elseif t == "FIRST_KILL" then return "First " .. tostring(ev.name) .. " slain"
  elseif t == "OBJECTIVE_COMPLETE" then
    return tostring(ev.text or "Objective complete") .. (ev.title and (" — " .. ev.title) or "")
  elseif t == "MARK" then return "Marked moment"
  end
  return t
end

function J.RecentEvents(n)
  local s = ns.session
  local out = {}
  if not s then return out end
  local total = #s.events
  for i = math.max(1, total - n + 1), total do
    table.insert(out, s.events[i])
  end
  return out
end

function J.Stats()
  local s = ns.session
  if not s then return nil end
  local c = s.counters
  local loc = ns.GetLocation()
  return {
    played = ns.PlayedSeconds(),
    area = loc.subzone or loc.zone or "—",
    zone = loc.zone,
    level = ns.Clean(ns.SafeCall(UnitLevel, "player")) or s.character.endLevel or "?",
    questsCompleted = c.questsCompleted or 0,
    questsAccepted = c.questsAccepted or 0,
    places = #s.zones,
    deaths = c.deaths or 0,
    people = #s.people,
    kills = c.kills or 0,
    xp = c.xpGained or 0,
    notes = c.notes or 0,
    marks = c.marks or 0,
    levelsGained = c.levelsGained or 0,
  }
end

function J.PeopleSummary()
  local s = ns.session
  local out = {}
  if not s then return out end
  local now = GetTime()
  for _, p in ipairs(s.people) do
    local secs = p.seconds or 0
    local g = ns.currentGroup[p.name]
    if g then secs = secs + (now - g.since) end
    table.insert(out, { name = p.name, class = p.class, minutes = math.floor(secs / 60 + 0.5) })
  end
  table.sort(out, function(a, b) return a.minutes > b.minutes end)
  return out
end

function J.StatusLine()
  local st = J.Stats()
  if not st then return "no session yet" end
  return string.format("%s in %s — Lv %s · %d quests · %d places · %d kills · %d deaths · %d people · %d notes",
    ns.FormatDuration(st.played), tostring(st.area), tostring(st.level), st.questsCompleted, st.places,
    st.kills, st.deaths, st.people, st.notes + st.marks)
end
