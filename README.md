# EPL Analyst

A chatbot for Premier League questions: tables at any matchday, scorelines, top scorers, cards and
more, covering 1992/93 to 2025/26. It writes SQL against a real database (`epl.db`), so the numbers
come from the data and not from the model's memory. It runs on Groq's free API tier, so there is no
per-question cost.

## What it knows

| Seasons | What's in the data |
|---|---|
| 1992/93 - 2019/20 | Results, table at any matchday, goals, assists, cards, substitutions, lineups |
| 2020/21 - 2024/25 | Results, table at any matchday, and each season's Golden Boot winner. No other player stats |
| 2025/26 | Results, table at any matchday, goals and cards. No assists, substitutions or lineups |

When someone asks for something outside that (say, assists in 2025/26), the bot does not guess. It
answers "I do not have data regarding this", says exactly what is missing, and lists what it does have
for each season. Two layers handle this, so it does not depend on the model behaving:

1. A check on the question itself catches obvious cases (a stat plus a season that lacks it, a season
   outside the data) and replies straight away without calling the model.
2. A check on every SQL query the model writes blocks lookups of player data for seasons where it
   cannot exist, and adds a caveat when a query spans seasons with uneven coverage.

Everything about coverage lives in `backend/data_coverage.py`. If you add data later, change the
`TIERS` list there and the replies, the checks and the coverage panel in the app all follow.

Data notes:
- Assists for 1992/93 - 2019/20 come from a scraped premierleague.com dataset, not an official feed.
- 2025/26 player names were upper-cased in the source (`Erling HAALAND`) and have been cleaned up.
- `game_week` is the originally scheduled matchday and is empty for 2025/26. The
  `standings_by_matchday` table is what answers "table after matchday N" for every season.
- Sources: TimHoare/Premier_League_Data (1992/93 - 2019/20) and openfootball/england (2020/21 - 2025/26).
  Golden Boot winners for 2020/21 - 2024/25 were added by hand and checked against several published lists.

## Run it on your computer

1. Get a free Groq key (no card needed) at https://console.groq.com, under API Keys.
2. In this folder:

   ```powershell
   pip install -r requirements.txt
   copy .streamlit\secrets.toml.example .streamlit\secrets.toml
   ```
   Open `.streamlit\secrets.toml` and paste your key in.
3. Start it:

   ```powershell
   python -m streamlit run streamlit_app.py
   ```
   It opens at http://localhost:8501.

## Put it online (Streamlit Community Cloud, free)

1. Push this folder to a GitHub repo. `epl.db` is about 72 MB, under GitHub's 100 MB limit (you may
   get a size warning, it still pushes). `.gitignore` keeps your real `secrets.toml` out of the repo.
2. At https://share.streamlit.io sign in with GitHub, click **Create app**, pick the repo, and set the
   main file to `streamlit_app.py`.
3. Open **Advanced settings, then Secrets**, and paste:

   ```
   GROQ_API_KEY = "gsk_your-real-key"
   EPL_MODEL = "openai/gpt-oss-120b"
   ```
4. Deploy. You get a `https://<name>.streamlit.app` link that works on phones and laptops, and
   visitors never see or need a key.

What to expect on the free setup:
- Everyone shares your one Groq quota (around 30 requests a minute). When it runs out the app says so
  and asks people to try again shortly.
- The app sleeps when nobody has used it for a while and takes a few seconds to wake up.
- Groq retires models now and then. If the app says the model was retired, pick a current one from
  https://console.groq.com/docs/models and change `EPL_MODEL` in Secrets. No code change needed.
- The fonts load from Google Fonts. If a visitor's network blocks that, the page falls back to
  system fonts and still works.

## The interface

The page is built with a custom stylesheet (`assets/style.css`) on top of Streamlit. It is laid out for
phones first: single column, large tap targets, 16px input text so iOS does not zoom, the input
respects the iPhone home-bar inset, and animations switch off for people who have reduced motion set.
The landing view shows live numbers from the database and a ticker of every season's champion. Each
answer has a "How I got this" panel with the real rows and the SQL, so any number can be checked.

The CSS targets Streamlit's own element names. A big Streamlit update can rename some of them, so if
the look breaks after upgrading, that is the first place to check.

## Files

- `streamlit_app.py` - the app
- `ui_components.py` - HTML pieces for the landing page and coverage panel
- `assets/style.css` - all the styling
- `backend/agent.py` - the question to SQL to answer loop (read-only, one SELECT at a time)
- `backend/data_coverage.py` - what data exists, and the no-data checks
- `backend/schema.py` - the schema and rules the model is given
- `epl.db` - the database
- `backend/main.py`, `frontend/`, `Dockerfile`, `render.yaml` - an older FastAPI version of the same bot,
  still working, in case you want a plain API instead of Streamlit
