from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from memo.services import fs, organizer
from memo.services.ollama_client import get_client
from memo.settings import settings

router = APIRouter(prefix="/organize", tags=["organize"])


class AnalyzeRequest(BaseModel):
    folder: str
    include_subfolders: bool = False
    paths: list[str] | None = None  # if set, analyze only these files (ignore folder scan)


class ClusterPlan(BaseModel):
    folder_name: str
    files: list[str]


class ApplyRequest(BaseModel):
    folder: str
    plan: list[ClusterPlan]


@router.post("/analyze")
async def analyze_folder(body: AnalyzeRequest) -> dict:
    abs_folder = os.path.abspath(body.folder)
    if not os.path.isdir(abs_folder):
        raise HTTPException(status_code=400, detail=f"Not a directory: {body.folder!r}")
    ollama = get_client()
    try:
        result = await organizer.analyze(
            folder=abs_folder,
            include_subfolders=body.include_subfolders,
            ollama=ollama,
            embed_model=settings.embed_model,
            paths=body.paths,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


@router.post("/apply")
def apply_organization(body: ApplyRequest) -> dict:
    abs_folder = os.path.abspath(body.folder)
    if not os.path.isdir(abs_folder):
        raise HTTPException(status_code=400, detail=f"Not a directory: {body.folder!r}")
    plan = [{"folder_name": c.folder_name, "files": c.files} for c in body.plan]
    try:
        result = fs.apply_organization(abs_folder, plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
