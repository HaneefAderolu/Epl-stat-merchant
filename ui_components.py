"""HTML pieces for the Streamlit UI. Kept out of streamlit_app.py so the page logic stays readable.

Everything returned here is built without leading indentation or blank lines on purpose:
Streamlit runs st.markdown through a Markdown parser first, and indented or blank-separated
HTML turns into code blocks.
"""
from __future__ import annotations

import sqlite3
from html import escape

import data_coverage as cov

BALL_SVG = (
    '<svg class="ball" viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">'
    '<circle cx="16" cy="16" r="14" fill="#F4F1E8" stroke="#0B2018" stroke-width="2"/>'
    '<polygon points="16,10 21.7,14.1 19.5,20.9 12.5,20.9 10.3,14.1" fill="#0B2018"/>'
    '<path d="M16 10V4.5M21.7 14.1l5.2-1.7M19.5 20.9l3.3 4.5M12.5 20.9l-3.3 4.5M10.3 14.1l-5.2-1.7" '
    'stroke="#0B2018" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>'
)

_CHAMPIONS_SQL = """
SELECT s.season, s.team
FROM standings_by_matchday s
JOIN (SELECT season, MAX(matches_played) mp FROM standings_by_matchday GROUP BY season) m
  ON s.season = m.season AND s.matches_played = m.mp
WHERE s.position = 1
ORDER BY s.season
"""


def load_site_stats(db_path: str) -> dict:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        seasons = con.execute("SELECT COUNT(DISTINCT season) FROM matches").fetchone()[0]
        matches = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        goals = con.execute("SELECT SUM(home_score + away_score) FROM matches").fetchone()[0] or 0
        clubs = con.execute("SELECT COUNT(DISTINCT team) FROM standings_by_matchday").fetchone()[0]
        champions = con.execute(_CHAMPIONS_SQL).fetchall()
    finally:
        con.close()
    return {"seasons": seasons, "matches": matches, "goals": goals, "clubs": clubs, "champions": champions}


def hero_html(stats: dict) -> str:
    first = cov.season_label(cov.FIRST_YEAR)
    last = cov.season_label(cov.LAST_YEAR)
    return (
        '<section class="hero">'
        '<div class="pitch-deco"><span class="pd-circle"></span><span class="pd-line"></span></div>'
        f'<div class="kicker"><span class="live-dot"></span>{stats["seasons"]} seasons, {first} to {last}</div>'
        f'<div class="brandline">{BALL_SVG}<span>EPL Analyst</span></div>'
        '<h1 class="hero-title">Every Premier League question, answered from the data.</h1>'
        '<p class="hero-sub">Tables at any matchday, scorelines, top scorers, cards and more. '
        'Each answer is a real lookup in the match database, so the numbers are exact.</p>'
        '</section>'
    )


def tiles_html(stats: dict) -> str:
    items = [
        (f'{stats["seasons"]}', "seasons"),
        (f'{stats["matches"]:,}', "matches"),
        (f'{stats["goals"]:,}', "goals"),
        (f'{stats["clubs"]}', "clubs"),
    ]
    tiles = "".join(
        f'<div class="tile"><div class="tile-num">{n}</div><div class="tile-lbl">{lbl}</div></div>'
        for n, lbl in items
    )
    return f'<div class="tiles">{tiles}</div>'


def ticker_html(champions: list[tuple[str, str]]) -> str:
    def item(season: str, team: str) -> str:
        return f'<span class="tk"><b>{escape(season[2:])}</b>{escape(team)}</span>'

    track = "".join(item(s, t) for s, t in champions)
    return (
        '<div class="ticker" role="marquee" aria-label="League champions by season">'
        '<span class="ticker-tag">Champions</span>'
        f'<div class="ticker-window"><div class="ticker-track">{track}{track}</div></div>'
        '</div>'
    )


def coverage_html() -> str:
    cards = []
    for t in cov.TIERS:
        chips = "".join(
            f'<span class="cap {"ok" if key in t["caps"] else "no"}">{label}</span>'
            for key, label, _ in cov.CAPABILITIES
        )
        cards.append(
            '<div class="tier">'
            f'<div class="tier-head"><span class="tier-years">{cov.tier_label(t)}</span>'
            f'<span class="tier-name">{t["name"]}</span></div>'
            f'<div class="caps">{chips}</div></div>'
        )
    return (
        '<div class="coverage">'
        '<div class="coverage-title">What I can answer, by season</div>'
        f'<div class="tiers">{"".join(cards)}</div>'
        '<p class="coverage-note">Assists before 2020 come from a scraped premierleague.com dataset, '
        'not an official feed. If you ask for something outside this, I will say so and show this list.</p>'
        '</div>'
    )


def topbar_html() -> str:
    first = cov.season_label(cov.FIRST_YEAR)
    last = cov.season_label(cov.LAST_YEAR)
    return (
        '<div class="topbar">'
        f'<div class="brandline small">{BALL_SVG}<span>EPL Analyst</span></div>'
        f'<div class="range-pill">{first} to {last}</div>'
        '</div>'
    )


def thinking_html() -> str:
    return (
        '<div class="thinking" role="status" aria-live="polite">'
        '<span class="ball-bounce">⚽</span>'
        '<span class="think-text">Checking the database</span>'
        '<span class="dots"><i></i><i></i><i></i></span>'
        '</div>'
    )


def nodata_badge_html() -> str:
    return '<div class="nodata-badge"><span></span>No data for this</div>'


def error_badge_html() -> str:
    return '<div class="error-badge"><span></span>Something went wrong</div>'
