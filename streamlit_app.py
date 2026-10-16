import inspect
import os
import re
import sys
import time
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

# Groq key from Streamlit secrets (Community Cloud: app settings -> Secrets), else a normal env var.
try:
    if "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
    if "EPL_MODEL" in st.secrets:
        os.environ["EPL_MODEL"] = st.secrets["EPL_MODEL"]
except Exception:
    pass  # no secrets file locally is fine

import ui_components as ui  # noqa: E402
from agent import DB_PATH, ask_detailed  # noqa: E402

st.set_page_config(
    page_title="EPL Analyst",
    page_icon="⚽",
    layout="centered",
    initial_sidebar_state="collapsed",
)
st.markdown(f"<style>{(ROOT / 'assets' / 'style.css').read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True)


def _stretch(fn):
    """Full-width kwargs that work on both older and newer Streamlit versions."""
    params = inspect.signature(fn).parameters
    if "width" in params:
        return {"width": "stretch"}
    if "use_container_width" in params:
        return {"use_container_width": True}
    return {}


@st.cache_data(show_spinner=False)
def site_stats() -> dict:
    return ui.load_site_stats(str(DB_PATH))


EXAMPLES = [
    ("🏆", "Who won the Golden Boot in 1993/94?"),
    ("📊", "What was Arsenal's points total after matchday 20 in 2025/26?"),
    ("⚽", "Who were the top five scorers in 2025/26?"),
    ("🟥", "Which player got the most red cards in 2009/10?"),
    ("📅", "Show Manchester United's results in April 2013"),
    ("🔎", "Who got the most assists in 2025/26?"),
]

S = st.session_state
S.setdefault("chat", [])        # rendered messages
S.setdefault("history", None)   # model conversation, including tool calls
S.setdefault("pending", None)   # question waiting for an answer


def submit(question: str) -> None:
    S.chat.append({"role": "user", "content": question})
    S.pending = question


def reset_chat() -> None:
    S.chat, S.history, S.pending = [], None, None


def friendly_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "api_key" in low or "401" in msg or "invalid api key" in low:
        return "The server's Groq API key is missing or invalid."
    if "429" in msg or "rate limit" in low or "rate_limit" in low:
        return "The free Groq quota is used up for the moment. Try again in a minute."
    if "model_not_found" in low or "decommission" in low:
        return "The configured Groq model has been retired. Set EPL_MODEL to a current model."
    return msg[:300]


def typewriter(text: str):
    parts = re.split(r"(\s+)", text)
    delay = min(0.022, 1.3 / max(len(parts), 1))
    for p in parts:
        yield p
        time.sleep(delay)


def render_data(msg: dict) -> None:
    tables, sqls = msg.get("tables") or [], msg.get("sql") or []
    if not sqls:
        return
    n = len(sqls)
    with st.expander(f"How I got this ({n} {'query' if n == 1 else 'queries'})"):
        shown = {t["sql"]: t for t in tables}
        for i, q in enumerate(sqls, 1):
            t = shown.get(q)
            if t:
                note = f" ({len(t['rows'])} of {t['total']} rows shown)" if t["total"] > len(t["rows"]) else ""
                st.caption(f"Query {i}{note}")
                st.dataframe(pd.DataFrame(t["rows"], columns=t["columns"]), hide_index=True,
                             **_stretch(st.dataframe))
            else:
                st.caption(f"Query {i} (no rows returned)")
            st.code(q, language="sql")


def render_assistant_body(msg: dict, stream: bool = False) -> None:
    if msg.get("error"):
        st.markdown(ui.error_badge_html(), unsafe_allow_html=True)
    elif msg.get("no_data"):
        st.markdown(ui.nodata_badge_html(), unsafe_allow_html=True)
    text = msg["content"]
    if stream and len(text) < 1100 and "|" not in text:
        st.write_stream(typewriter(text))
    else:
        st.markdown(text)
    render_data(msg)


def render_message(msg: dict) -> None:
    if msg["role"] == "user":
        with st.chat_message("user", avatar="🙂"):
            # invisible tag the stylesheet uses to style and right-align user bubbles
            st.markdown('<span class="msg-user"></span>' + escape(msg["content"]), unsafe_allow_html=True)
    else:
        with st.chat_message("assistant", avatar="⚽"):
            render_assistant_body(msg)


# ------------------------------------------------------------------ page

PLACEHOLDER = "Ask about any season"
stats = site_stats()

if S.chat:
    # conversation view: input pinned to the bottom of the screen (must sit outside any container)
    prompt = st.chat_input(PLACEHOLDER, key="chat_prompt", disabled=bool(S.pending))
    if prompt and prompt.strip():
        submit(prompt.strip())

# Each mode renders into its own slot. Streamlit reuses a container between runs and only replaces
# its children index by index, so anything left over from the previous view stays on screen (faded)
# until the run finishes. Giving landing and chat separate slots means switching modes swaps cleanly,
# which matters here because the answer takes a few seconds and the old page would otherwise show.
landing_slot = st.empty()
chat_slot = st.empty()
with (chat_slot if S.chat else landing_slot).container():
    if S.chat:
        st.markdown(ui.topbar_html(), unsafe_allow_html=True)
        with st.container(key="toolbar"):
            c1, c2 = st.columns(2)
            with c1:
                with st.popover("Data coverage", **_stretch(st.popover)):
                    st.markdown(ui.coverage_html(), unsafe_allow_html=True)
            with c2:
                st.button("New chat", key="new_chat", on_click=reset_chat, **_stretch(st.button))
        for m in S.chat:
            render_message(m)
    else:
        # landing view: the input sits inline in the hero, so the page opens at the top
        st.markdown(ui.hero_html(stats), unsafe_allow_html=True)
        with st.container(key="hero_input"):
            hero_prompt = st.chat_input(PLACEHOLDER, key="hero_prompt")
        if hero_prompt and hero_prompt.strip():
            submit(hero_prompt.strip())
            st.rerun()
        st.markdown(ui.tiles_html(stats), unsafe_allow_html=True)
        st.markdown(ui.ticker_html(stats["champions"]), unsafe_allow_html=True)
        st.markdown('<div class="section-label">Try asking</div>', unsafe_allow_html=True)
        with st.container(key="examples"):
            for i, (emoji, q) in enumerate(EXAMPLES):
                st.button(f"{emoji}  {q}", key=f"ex{i}", on_click=submit, args=(q,), **_stretch(st.button))
        st.markdown(ui.coverage_html(), unsafe_allow_html=True)

    if S.pending:
        question = S.pending
        with st.chat_message("assistant", avatar="⚽"):
            slot = st.empty()
            slot.markdown(ui.thinking_html(), unsafe_allow_html=True)
            try:
                res = ask_detailed(question, S.history)
                S.history = res["history"]
                reply = {"role": "assistant", "content": res["answer"], "sql": res["sql"],
                         "tables": res["tables"], "no_data": res["no_data"]}
            except Exception as e:  # keep the page alive and tell the user what happened
                reply = {"role": "assistant", "content": friendly_error(e), "error": True}
            slot.empty()
            render_assistant_body(reply, stream=True)
        S.chat.append(reply)
        S.pending = None
        st.rerun()
