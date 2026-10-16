import json
import os
import re
import sqlite3
from pathlib import Path

from openai import OpenAI

import data_coverage as cov
from schema import SCHEMA_DESCRIPTION

DB_PATH = Path(__file__).resolve().parent.parent / "epl.db"

# Groq's API is OpenAI-compatible, so the official `openai` SDK works unmodified —
# just point base_url at Groq and use a Groq model id. Free tier, no credit card:
# get a key at https://console.groq.com
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.environ.get("EPL_MODEL", "openai/gpt-oss-120b")
MAX_ROWS_RETURNED = 300
MAX_TOOL_ROUNDS = 6  # safety cap so a confused model can't loop forever
MAX_TABLE_ROWS_SHOWN = 60  # rows kept per query for the UI's data view

_client = None


def get_client() -> OpenAI:
    """Create the API client on first use so the key can be set after import
    (Streamlit loads it from st.secrets at runtime, FastAPI from the environment)."""
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("GROQ_API_KEY") or "unset", base_url=GROQ_BASE_URL)
    return _client


SYSTEM_PROMPT = f"""You are the EPL Analyst, a chat assistant that answers questions about the English \
Premier League using a fixed SQLite dataset — nothing else. You have one tool, run_sql, which runs a \
single read-only SELECT statement against the database and returns the rows.

{SCHEMA_DESCRIPTION}

DATA COVERAGE
{cov.coverage_text()}

HOW TO ANSWER
- Always use run_sql to get real numbers before answering any factual question about matches, standings,
  players, goals, assists, cards, or appearances. Never answer a stats question from memory.
- Once you have the data you need, answer in plain, natural, conversational English. Lead with the answer,
  then a bit of supporting detail if useful. Don't dump raw tables unless the person asked for a list — a
  handful of rows can be given as a short prose list or a compact markdown table if that's genuinely clearer.
- If a question is ambiguous (e.g. "top scorer" without a season), ask a brief clarifying question instead
  of guessing, unless a reasonable default is obvious (e.g. "top scorer" alongside an already-established
  season in the conversation).
- If a question is outside the dataset's scope (wrong sport, outside 1992/93-2025/26, a player-level stat
  for a 2020/21-2024/25 season, or a stat this data doesn't track like transfer fees), say so directly and
  briefly — don't apologize at length.
- Keep answers concise by default. This is a chat, not a report.
- Data that does not exist: if the user asks for something this database does not contain (see the
  coverage below), start your reply with exactly "I do not have data regarding this." then say what is
  missing, then list what you do have, season by season. Never guess and never present an empty result
  as if it were a real answer.
- If a tool result contains a "coverage_note", pass that caveat on to the user in one sentence.
- golden_boot_winners only holds the league-wide winner(s) for 2020/21 to 2024/25. It cannot answer a
  question about one club's top scorer, runners-up, or any other player's goals in those seasons.
- The newest season in the data is 2025/26. Anything later is not in the data.
- Call run_sql again if your first query errors or comes back empty and you suspect a spelling/format
  issue (e.g. team name, season format) — don't give up after one failed query without trying to fix it.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": (
                "Execute a single read-only SQL SELECT statement against the Premier League SQLite "
                "database and return the matching rows. Only SELECT statements are permitted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single SQLite SELECT statement. No semicolon-chained statements.",
                    }
                },
                "required": ["sql"],
            },
        },
    }
]

_BANNED_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "attach", "detach",
    "pragma", "replace", "create", "vacuum", "reindex", "trigger",
)


def _is_safe_select(sql: str) -> bool:
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        return False  # no stacked statements
    if not re.match(r"(?is)^\s*select\b", s):
        return False
    low = s.lower()
    return not any(re.search(rf"\b{kw}\b", low) for kw in _BANNED_KEYWORDS)


def run_sql(sql: str) -> dict:
    if not _is_safe_select(sql):
        return {"error": "Only a single read-only SELECT statement is allowed."}
    con = None
    try:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(sql)
        rows = cur.fetchmany(MAX_ROWS_RETURNED)
        cols = [d[0] for d in cur.description] if cur.description else []
        return {
            "columns": cols,
            "rows": [dict(r) for r in rows],
            "returned_row_count": len(rows),
            "truncated": len(rows) == MAX_ROWS_RETURNED,
        }
    except sqlite3.Error as e:
        return {"error": str(e)}
    finally:
        if con is not None:
            con.close()


def _new_history() -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def _finish_without_model(messages, question, answer, kind):
    messages.append({"role": "user", "content": question})
    messages.append({"role": "assistant", "content": answer})
    return {"answer": answer, "history": messages, "sql": [], "tables": [],
            "no_data": kind == "block", "kind": kind}


def ask_detailed(question: str, history: list[dict] | None = None) -> dict:
    """
    Run one user turn through the agent loop.

    history: prior message list in OpenAI chat-completions format (incl. the leading system
             message), or None to start a fresh conversation.
    Returns {answer, history, sql, tables, no_data, kind}. `tables` holds the rows each query
    returned so a UI can show the underlying data. `no_data` is True when the reply is the
    "I do not have data regarding this" answer.
    """
    messages = list(history) if history else _new_history()

    # 1) Cheap deterministic check before spending a model call.
    pre = cov.precheck(question)
    if pre["kind"] in ("coverage", "block"):
        return _finish_without_model(messages, question, pre["message"], pre["kind"])

    user_content = question if pre["kind"] != "hint" else f"{question}\n\n{pre['hint']}"
    messages.append({"role": "user", "content": user_content})

    sql_log: list[str] = []
    tables: list[dict] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            tool_choice="auto",
            messages=messages,
        )
        msg = response.choices[0].message

        # Keep the assistant turn as plain dicts so history stays JSON-serializable.
        assistant_entry = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            answer = (msg.content or "").strip()
            no_data = answer.lower().startswith("i do not have data")
            return {"answer": answer, "history": messages, "sql": sql_log, "tables": tables,
                    "no_data": no_data, "kind": "answer"}

        blocked: dict[str, list[int]] = {}
        any_ok = False
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            sql = args.get("sql", "")
            sql_log.append(sql)

            # 2) Backstop: stop queries for player data that cannot exist for those seasons.
            gate = cov.check_sql(sql)
            if gate and gate["block"]:
                blocked.setdefault(gate["stat"], []).extend(gate["seasons"])
                result = {"error": "NO_DATA",
                          "detail": "This database has no such data for those seasons. "
                                    "Do not try other tables to work around it."}
            else:
                result = run_sql(sql)
                if "error" not in result:
                    any_ok = True
                    if result.get("rows"):
                        tables.append({"sql": sql, "columns": result["columns"],
                                       "rows": result["rows"][:MAX_TABLE_ROWS_SHOWN],
                                       "total": result["returned_row_count"]})
                if gate and gate.get("note"):
                    result["coverage_note"] = gate["note"]

            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, default=str)[:12000]})

        if blocked and not any_ok:
            answer = cov.no_data_message({k: sorted(set(v)) for k, v in blocked.items()})
            messages.append({"role": "assistant", "content": answer})
            return {"answer": answer, "history": messages, "sql": sql_log, "tables": [],
                    "no_data": True, "kind": "block"}

    return {
        "answer": "I wasn't able to pin down a confident answer to that in a reasonable number of steps. "
                  "Could you rephrase it or narrow it down (a specific season or team)?",
        "history": messages, "sql": sql_log, "tables": tables, "no_data": False, "kind": "gave_up",
    }


def ask(question: str, history: list[dict] | None = None) -> tuple[str, list[dict], list[str]]:
    """Backward-compatible wrapper used by the FastAPI version."""
    r = ask_detailed(question, history)
    return r["answer"], r["history"], r["sql"]
