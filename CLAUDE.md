# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands assume PowerShell on Windows.

**First-time setup:**
```powershell
# Backend
cd src\backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"

# Frontend
cd src\frontend
npm install
```

**Dev mode (runs entire app):**
```powershell
# from src/frontend/
npm run tauri dev
```

**Run tests:**
```powershell
# from src/backend/
.venv\Scripts\python -m pytest tests\unit -v
```

**TypeScript check:**
```powershell
# from src/frontend/
npx tsc --noEmit
```

## Architecture

Three-layer desktop app: **Tauri 2 shell** wraps a **React/TypeScript frontend** and manages a **Python FastAPI backend** as a sidecar process.

**Backend** (`src/backend/memo/`): FastAPI on a dynamically selected port. On startup (`main.py:main()`), it binds to a free port, prints `MEMO_PORT=<n>` to stdout, and uvicorn starts. The Tauri Rust layer reads this line and exposes the port via the `get_backend_port` IPC command.

**Frontend** (`src/frontend/src/`): Vite + React 18 on port 1420 during dev. Discovers the backend port via Tauri IPC through `src/ipc/backend.ts:getBackendPort()`, which polls for up to 10 seconds.

**Data layer:**
- SQLite via SQLAlchemy — `db/models.py` holds `IndexState`, `Chat`, `Message`
- ChromaDB for vector storage — persisted in `src/backend/data/chroma/`
- Documents processed by `services/document_loader.py` (PDF/DOCX/MD/TXT) → chunked in `services/indexer.py` → embedded via Ollama → stored in ChromaDB

**File watching:** `services/watcher.py` starts/stops via FastAPI lifespan events in `main.py`.

**Streaming:** Long-running operations (e.g., `/api/index`) use SSE (Server-Sent Events) for progress updates.

## Prerequisites

- **Ollama** must be running locally with these models pulled:
  - `ollama pull bge-m3` — embeddings (required)
  - `ollama pull qwen3:1.7b` — auto-naming (required)
  - `ollama pull qwen3:4b` — chat (recommended for Stage 2+)

## Backend environment variables

All use the `MEMO_` prefix (configured in `src/backend/memo/settings.py`):

| Variable | Default | Purpose |
|---|---|---|
| `MEMO_OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `MEMO_DATA_DIR` | `./data` | SQLite + ChromaDB storage |
| `MEMO_EMBED_MODEL` | `bge-m3` | Embedding model |
| `MEMO_NAME_MODEL` | `qwen3:1.7b` | Auto-naming model |

## Implementation status

- **Stage 0–1** complete: skeleton + document indexing pipeline
- **Stage 2–4** planned: Q&A chat, auto-organization, document generation
