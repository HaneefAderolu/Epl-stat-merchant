"""What the database contains, in one place.

The agent uses this to say "I do not have data regarding this" properly (instead of guessing or
returning an empty result), and the Streamlit UI uses it to draw the coverage panel.
If the data ever changes, change TIERS and everything else follows.
"""
from __future__ import annotations

import re

FIRST_YEAR = 1992   # start year of the oldest season (1992/93)
LAST_YEAR = 2025    # start year of the newest season (2025/26)

# key, short label (UI chips), phrase used inside sentences
CAPABILITIES = [
    ("results", "Results", "results"),
    ("tables", "Tables", "the table at any matchday"),
    ("golden_boot", "Golden Boot", "the Golden Boot winner"),
    ("goals", "Player goals", "goals by player"),
    ("assists", "Assists", "assists"),
    ("cards", "Cards", "cards"),
    ("substitutions", "Subs", "substitutions"),
    ("lineups", "Lineups", "lineups and appearances"),
]
_ALL = {c[0] for c in CAPABILITIES}

TIERS = [
    {
        "start": 1992, "end": 2019, "name": "Full detail", "caps": set(_ALL),
        "summary": "results, the table at any matchday, goals, assists, cards, substitutions, "
                   "lineups and appearances",
    },
    {
        "start": 2020, "end": 2024, "name": "Results and tables",
        "caps": {"results", "tables", "golden_boot"},
        "summary": "results, the table at any matchday, and the Golden Boot winner of each season "
                   "(no other player stats)",
    },
    {
        "start": 2025, "end": 2025, "name": "Results, goals and cards",
        "caps": {"results", "tables", "golden_boot", "goals", "cards"},
        "summary": "results, the table at any matchday, goals and cards "
                   "(no assists, substitutions or lineups)",
    },
]

# how a missing stat is worded in the "I have no ..." sentence
_STAT_PHRASE = {
    "assists": "assists",
    "cards": "cards",
    "goals": "player goals",
    "substitutions": "substitutions",
    "lineups": "lineups and appearances",
    "events": "player goals and cards",
    "results": "data at all",
}


def season_label(year: int) -> str:
    return f"{year}/{(year + 1) % 100:02d}"


def tier_label(tier: dict) -> str:
    if tier["start"] == tier["end"]:
        return season_label(tier["start"])
    return f"{season_label(tier['start'])} to {season_label(tier['end'])}"


def has(stat: str, year: int) -> bool:
    """Is this kind of data present for the season that starts in `year`?"""
    if year < FIRST_YEAR or year > LAST_YEAR:
        return False
    if stat == "events":          # generic player-event query (goals or cards)
        stat = "goals"
    for t in TIERS:
        if t["start"] <= year <= t["end"]:
            return stat in t["caps"]
    return False


def _join_and(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def fmt_seasons(years) -> str:
    """[2020, 2021, 2022, 2025] -> '2020/21 to 2022/23 and 2025/26'"""
    ys = sorted(set(years))
    runs: list[list[int]] = []
    for y in ys:
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    parts = []
    for r in runs:
        if len(r) == 1:
            parts.append(season_label(r[0]))
        elif len(r) == 2:
            parts.extend([season_label(r[0]), season_label(r[1])])
        else:
            parts.append(f"{season_label(r[0])} to {season_label(r[-1])}")
    return _join_and(parts)


def coverage_text() -> str:
    lines = ["**Here is what I do have, season by season:**"]
    for t in TIERS:
        lines.append(f"- **{tier_label(t)}:** {t['summary']}")
    return "\n".join(lines)


def no_data_message(missing: dict[str, list[int]], out_of_range: list[int] | None = None) -> str:
    phrases = []
    for stat, years in missing.items():
        phrases.append(f"no {_STAT_PHRASE.get(stat, stat)} for {fmt_seasons(years)}")
    if out_of_range:
        phrases.append(
            f"no data at all for {fmt_seasons(out_of_range)} "
            f"(my data covers {season_label(FIRST_YEAR)} to {season_label(LAST_YEAR)})"
        )
    sentence = "I have " + _join_and(phrases) + "."
    return (
        "I do not have data regarding this.\n\n"
        f"{sentence}\n\n"
        f"{coverage_text()}\n\n"
        "Ask me about any of these and I will look it up."
    )


# ---------------------------------------------------------------- question pre-check

_SEASON_4 = re.compile(r"(?<![\d/])((?:19|20)\d{2})\s*[/\-\u2013]\s*((?:19|20)?\d{2})(?![\d/])")
_SEASON_2 = re.compile(r"(?<![\d/\-])(\d{2})\s*/\s*(\d{2})(?![\d/])")


def parse_seasons(text: str) -> list[int]:
    """Season start years mentioned in free text: 2025/26, 2025-26, 1999/2000, 25/26 ..."""
    years: set[int] = set()
    for m in _SEASON_4.finditer(text):
        y, end = int(m.group(1)), int(m.group(2)[-2:])
        if end == (y + 1) % 100:
            years.add(y)
    for m in _SEASON_2.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if b == (a + 1) % 100:
            years.add(1900 + a if a >= 80 else 2000 + a)
    return sorted(years)


_STAT_PATTERNS = [
    ("assists", re.compile(r"\bassists?\b|\bassisted\b|\bplaymaker\b", re.I)),
    ("substitutions", re.compile(r"\bsubstitut\w*|\bsubs\b|\bsubbed\b|\bcame (?:on|off)\b|\bfrom the bench\b", re.I)),
    ("lineups", re.compile(
        r"\bline-?ups?\b|\bstarting (?:xi|eleven|11)\b|\bappearances?\b|\bcaptain\w*|"
        r"\bminutes played\b|\bsquad\b", re.I)),
    ("cards", re.compile(
        r"\byellows?\b|\bred cards?\b|\bbookings?\b|\bbooked\b|\bsent off\b|\bcards?\b|\bdismissals?\b", re.I)),
]
_OTHER_INTENT = re.compile(
    r"golden boot|top scorer|champion|\btable\b|standing|\bpoints\b|position|finish|result|"
    r"\bscore|\bgoals?\b|\bwon\b|\bwin\b|\bwins\b|league", re.I)
_COVERAGE_Q = re.compile(
    r"\bwhat (?:data|seasons?|stats|statistics|info\w*)\b.{0,40}\b(?:have|cover\w*|include\w*|available)\b|"
    r"\bwhat (?:can|could) (?:i|you)\b|\bdata coverage\b|\bwhich seasons\b|"
    r"\bwhat do you (?:have|know|cover)\b|\bwhat are you able\b|\bhow far back\b", re.I)


def detect_stats(text: str) -> list[str]:
    return [key for key, pat in _STAT_PATTERNS if pat.search(text)]


def precheck(question: str) -> dict:
    """Decide, before any model call, whether the question can be answered from this data.

    kind = "pass"      nothing to flag
           "coverage"  the user asked what data exists
           "block"     every season mentioned lacks the requested data -> reply directly, no model call
           "hint"      some seasons lack it -> let the model answer the rest, with a coverage note
    """
    q = question.strip()
    if _COVERAGE_Q.search(q):
        return {"kind": "coverage", "message": "Here is everything I cover.\n\n" + coverage_text()}

    years = parse_seasons(q)
    if not years:
        return {"kind": "pass"}

    stats = detect_stats(q) or ["results"]
    missing: dict[str, list[int]] = {}
    out_of_range: list[int] = []
    ok_years: list[int] = []
    for y in years:
        if y < FIRST_YEAR or y > LAST_YEAR:
            out_of_range.append(y)
            continue
        bad = [s for s in stats if not has(s, y)]
        for s in bad:
            missing.setdefault(s, []).append(y)
        if not bad:
            ok_years.append(y)

    if not missing and not out_of_range:
        return {"kind": "pass"}

    message = no_data_message(missing, out_of_range)
    if not ok_years and (out_of_range or not _OTHER_INTENT.search(q)):
        return {"kind": "block", "message": message, "missing": missing, "out_of_range": out_of_range}

    # mixed question: some part is answerable, so let the model do that part
    gaps = [f"{_STAT_PHRASE.get(s, s)} for {fmt_seasons(y)}" for s, y in missing.items()]
    if out_of_range:
        gaps.append(f"any data for {fmt_seasons(out_of_range)}")
    hint = (
        f"[Coverage note: this database has no {_join_and(gaps)}. Answer whatever part of the question "
        "the data can support. For the part it cannot, say 'I do not have data regarding this' and list "
        "what data you do have, season by season.]"
    )
    return {"kind": "hint", "hint": hint, "missing": missing, "out_of_range": out_of_range}


# ---------------------------------------------------------------- SQL gate

_SQL_SEASON = re.compile(r"'(\d{4})/(\d{2})'")
_SQL_RANGE_OP = re.compile(r"season\s*(?:>=|<=|>|<|between|like|not\s+in)", re.I)


def _tier_overview() -> str:
    return "; ".join(f"{tier_label(t)}: {t['summary']}" for t in TIERS)


def check_sql(sql: str) -> dict | None:
    """Look at a query the model wants to run against the player-level tables.

    Returns None when fine, {"block": True, ...} when the data cannot exist for the seasons asked
    about, or {"block": False, "note": ...} when the answer will only reflect part of the seasons.
    """
    low = sql.lower()
    uses_lineups = re.search(r"\blineups\b", low) is not None
    uses_events = re.search(r"\bevents\b", low) is not None
    if not (uses_lineups or uses_events):
        return None

    if uses_lineups:
        stat = "lineups"
    elif "assist" in low:
        stat = "assists"
    elif "substitution" in low:
        stat = "substitutions"
    elif "booking" in low or "card" in low:
        stat = "cards"
    elif "goal" in low or "penalty" in low:
        stat = "goals"
    else:
        stat = "events"

    years = sorted({int(m.group(1)) for m in _SQL_SEASON.finditer(sql)})
    is_range = _SQL_RANGE_OP.search(low) is not None

    if years and not is_range:
        unavailable = [y for y in years if not has(stat, y)]
        if unavailable and len(unavailable) == len(years):
            return {"block": True, "stat": stat, "seasons": unavailable}
        if unavailable:
            return {
                "block": False,
                "note": f"Player-level {_STAT_PHRASE.get(stat, stat)} data does not exist for "
                        f"{fmt_seasons(unavailable)}, so those seasons are missing from this result. "
                        "Tell the user that in one sentence.",
            }
        return None

    return {
        "block": False,
        "note": "This query is not limited to seasons that all have this data. Player-level data only "
                f"exists as follows: {_tier_overview()}. Tell the user in one sentence that the answer "
                "only reflects the seasons that have it.",
    }
