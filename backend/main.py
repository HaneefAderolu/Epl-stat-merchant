import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import ask

app = FastAPI(title="EPL Analyst")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Very simple in-memory session store: session_id -> Anthropic message history.
# Fine for a personal project / demo. Swap for redis or a DB if you need it to
# survive restarts or run across multiple server processes.
SESSIONS: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sql: list[str]


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "message cannot be empty")

    session_id = req.session_id or str(uuid.uuid4())
    history = SESSIONS.get(session_id, [])

    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(
            500,
            "GROQ_API_KEY is not set on the server. Get a free key at "
            "https://console.groq.com and set it in your environment before starting the backend.",
        )

    try:
        answer, updated_history, sql_log = ask(req.message, history)
    except Exception as e:  # keep the demo resilient; surface the error to the UI
        raise HTTPException(502, f"Upstream error talking to the model: {e}")

    SESSIONS[session_id] = updated_history
    return ChatResponse(session_id=session_id, answer=answer, sql=sql_log)


@app.post("/api/reset")
def reset(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True, "api_key_configured": os.environ.get("GROQ_API_KEY") is not None}


# --- serve the frontend ---
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
