import socket
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memo.api.chats import router as chats_router
from memo.api.fs import router as fs_router
from memo.api.generate import router as generate_router
from memo.api.health import router as health_router
from memo.api.index import router as index_router
from memo.api.models import router as models_router
from memo.api.organize import router as organize_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    import threading

    from memo.db.models import IndexState
    from memo.db.session import SessionLocal, init_db
    from memo.services import watcher
    from memo.services.indexer import reconcile_all
    from memo.services.ollama_client import close_client

    init_db()
    watcher.start()

    # Re-register watch dirs for all previously indexed files so that
    # file changes are detected even after a backend restart.
    with SessionLocal() as db:
        for row in db.query(IndexState).all():
            watcher.watch_dir(os.path.dirname(row.file_path))

    # Catch edits made while the backend was down (the watcher only sees live
    # events). Hashing runs off the event loop so startup isn't blocked.
    threading.Thread(target=reconcile_all, daemon=True).start()

    yield
    watcher.stop()
    await close_client()


app = FastAPI(title="memo", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(fs_router)
app.include_router(index_router)
app.include_router(models_router)
app.include_router(chats_router)
app.include_router(generate_router)
app.include_router(organize_router)


def main() -> None:
    # Bind + listen ourselves, THEN print the port: the kernel queues incoming
    # connections from listen() onward, so the frontend never sees a refused
    # connection even if it connects before uvicorn's accept loop is running.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sock.bind(("127.0.0.1", port))
    port = sock.getsockname()[1]
    sock.listen()

    print(f"MEMO_PORT={port}", flush=True)

    config = uvicorn.Config(app, log_level="warning")
    server = uvicorn.Server(config)
    server.run(sockets=[sock])


if __name__ == "__main__":
    main()
