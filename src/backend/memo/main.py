import socket
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from memo.api.fs import router as fs_router
from memo.api.health import router as health_router
from memo.api.index import router as index_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from memo.db.session import init_db
    from memo.services import watcher

    init_db()
    watcher.start()
    yield
    watcher.stop()


app = FastAPI(title="memo", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(fs_router)
app.include_router(index_router)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else _free_port()
    print(f"MEMO_PORT={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
