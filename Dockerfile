FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY epl.db ./epl.db

WORKDIR /app/backend

# Render/Railway/Fly all inject $PORT — fall back to 8000 for local docker run.
ENV PORT=8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
