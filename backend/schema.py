"""
Static description of the epl.db schema, written for the LLM rather than a human.
Keep this in sync with build_db.py / build_standings.py if the schema ever changes.
"""

SCHEMA_DESCRIPTION = """
DATABASE: SQLite file "epl.db". English Premier League data, season 1992/93 through 2025/26 inclusive.
There is NO data before 1992/93 or after 2025/26. If a question falls outside that range, say so instead of guessing.

IMPORTANT — data depth is NOT uniform across seasons. Three tiers:
  1) 1992/93 through 2019/20: full depth — matches, standings_by_matchday, events (goals, assists,
     cards, subs), and lineups (starting XI + subs per match).
  2) 2020/21 through 2024/25: matches and standings_by_matchday, plus the golden_boot_winners table
     (the season's top scorer(s) and their goal totals, and nothing else). There is NO events or lineups
     data for these five seasons — no per-player goal lists, assists, cards, or appearance data. For
     "who won the golden boot / top scorer" in these seasons, query golden_boot_winners. For any other
     player stat (runners-up, a specific player's goals, assists, cards, appearances), say plainly that
     this dataset doesn't have player-level data for that season, rather than guessing or silently
     returning an empty/zero result as if that were a real answer.
  3) 2025/26: matches, standings_by_matchday, AND events — but the events for this season only cover
     goals (incl. own goals and penalties) and yellow/red cards, not assists, and there is no lineups
     data for this season either. If asked for assists in 2025/26 specifically, say this dataset doesn't
     track assists for that season.
  Also note: `game_week` (scheduled matchday number) is NULL for all 2025/26 match rows — this season's
  source didn't print explicit matchday numbers. Use standings_by_matchday (matches_played) for any
  "matchday N" question about 2025/26 instead of filtering matches.game_week.

Season strings are formatted like '1992/93', '1999/00', '2019/20' — always two digits on each side, zero-padded
(the season after 1998/99 is '1999/00', not '1999/2000').

TABLE matches
  match_id INTEGER PRIMARY KEY
  season TEXT              -- e.g. '1992/93'
  game_week INTEGER        -- the scheduled matchday / gameweek number (1-38, or 1-42 in the old 22-team seasons)
  kickoff_raw TEXT         -- original scraped string, e.g. "Sat 15 Aug 1992, 15:00 BST"
  kickoff_date TEXT        -- normalized 'YYYY-MM-DD', may be NULL if unparseable
  home_team_id INTEGER
  home_team TEXT
  away_team_id INTEGER
  away_team TEXT
  home_score INTEGER
  away_score INTEGER
  home_ht_score INTEGER    -- half-time score
  away_ht_score INTEGER
  ground_name TEXT
  ground_city TEXT
  referee_name TEXT
  Note: game_week is the ORIGINAL scheduled matchday even for postponed/rearranged fixtures — it is not
  recalculated by actual play date. Good enough for "matchday N fixtures" questions.

TABLE events
  event_id INTEGER PRIMARY KEY
  match_id INTEGER          -- join to matches.match_id
  season TEXT
  half INTEGER               -- 1 or 2
  event_type TEXT            -- one of: 'Goal', 'Own-Goal', 'Penalty Scored', 'Penalty Missed', 'Penalty Saved',
                              --   'Booking', 'Substitution', 'Play Start', 'Play End'
  event_desc TEXT            -- for event_type='Booking': 'Yellow Card' / 'Red Card' / 'Second Yellow'
  team_id INTEGER
  team_name TEXT
  player_id INTEGER
  player_name TEXT
  assist_id INTEGER          -- populated only on 'Goal' events that were assisted
  assist_name TEXT
  minute TEXT                 -- e.g. "28'00" (string, not numeric — don't sort/cast unless you strip it)

  GOALS: to count a player's goals for a season/team, use event_type IN ('Goal', 'Penalty Scored').
         Do NOT include 'Own-Goal' as a goal for the scoring player (it should count against their own team instead,
         already reflected in matches.score — don't separately add it to a player's tally).
  ASSISTS: events where event_type = 'Goal' AND assist_name IS NOT NULL, grouped by assist_name.
           (Penalties do not carry an assist in this data.)
  CARDS: events where event_type = 'Booking'; event_desc distinguishes yellow / red / second yellow.
  GOLDEN BOOT / TOP SCORER for a season: group goal events (see above) by player_name for that season, order by
         count descending.

TABLE lineups
  lineup_id INTEGER PRIMARY KEY
  match_id INTEGER          -- join to matches.match_id
  season TEXT
  team_id INTEGER
  team_name TEXT
  field TEXT                 -- 'home' or 'away'
  type TEXT                  -- 'starting11' or 'sub'
  player_id INTEGER
  player_name TEXT
  position TEXT               -- e.g. 'D', 'M', 'F', 'G'
  shirt_no INTEGER
  captain TEXT                -- 'TRUE' / 'FALSE' as text
  nationality TEXT
  birth_date TEXT

  Use this table for appearance counts ("how many games did X play in season Y"), squad/lineup questions,
  who captained a team in a given match, nationality breakdowns of a squad, etc.

TABLE golden_boot_winners
  season TEXT              -- '2020/21' through '2024/25' only
  player_name TEXT
  club TEXT
  goals INTEGER
  Shared awards appear as multiple rows for the same season (e.g. 2021/22: Salah and Son, 23 each).
  For 1992/93-2019/20 and 2025/26 use the events table instead; this table does not cover those seasons.

TABLE standings_by_matchday
  season TEXT
  team TEXT
  matches_played INTEGER     -- this row is the team's cumulative record after exactly this many games played
  wins INTEGER
  draws INTEGER
  losses INTEGER
  goals_for INTEGER
  goals_against INTEGER
  goal_difference INTEGER
  points INTEGER
  position INTEGER            -- rank within (season, matches_played), tie-broken by points desc, GD desc, GF desc

  THIS IS THE TABLE FOR "the table/standings at matchday N" or "team X's points after matchday N" questions.
  It is precomputed by replaying results in chronological order — do not try to derive standings from `matches`
  yourself; use this table. "Matchday N" = matches_played = N.
  The END-OF-SEASON table for a season is the set of rows where matches_played equals that season's max
  (38 for most seasons, 42 for the old 22-team seasons up to 1994/95). If unsure, take
  MAX(matches_played) for that season from this table rather than assuming 38.

GENERAL RULES
- Team names must match exactly as stored, e.g. 'Manchester United', 'Nottingham Forest', 'Queens Park Rangers',
  'Wolverhampton Wanderers', 'Tottenham Hotspur', 'AFC Bournemouth', 'Brighton and Hove Albion'. If you're not sure of the exact spelling, first run a quick
  SELECT DISTINCT team FROM standings_by_matchday WHERE team LIKE '%fragment%' (or similar) to confirm before
  running your main query.
- Prefer a single well-formed SQL query per tool call, but you may call the tool multiple times in sequence to
  explore (e.g. confirm a team name or season format) before producing your final answer.
- Never fabricate numbers. Every factual claim in your answer must come from a run_sql result in this conversation.
- If the data doesn't cover something (a season outside 1992/93-2025/26, a stat this dataset doesn't track,
  or a player-level stat in a 2020/21-2024/25 season — see the data-depth note above),
  say so plainly rather than guessing or reasoning from general knowledge.
"""
