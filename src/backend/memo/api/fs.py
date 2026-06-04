import os

from fastapi import APIRouter, HTTPException

from memo.services import fs

router = APIRouter(prefix="/fs", tags=["fs"])


@router.get("/tree")
def get_tree(path: str, depth: int = 5) -> dict:
    abs_path = os.path.abspath(path)
    if not os.path.isdir(abs_path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path!r}")
    return fs.get_tree(abs_path, depth)
