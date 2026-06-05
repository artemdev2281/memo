import os

from memo.db.models import IndexState
from memo.db.session import SessionLocal


def get_tree(path: str, depth: int = 5) -> dict:
    abs_path = os.path.abspath(path)
    prefix = abs_path.rstrip("/\\") + os.sep
    with SessionLocal() as db:
        rows = db.query(IndexState).all()
        statuses = {
            r.file_path: r.status
            for r in rows
            if r.file_path == abs_path or r.file_path.startswith(prefix)
        }
    return _build_node(abs_path, depth, statuses)


def _build_node(path: str, depth: int, statuses: dict) -> dict:
    name = os.path.basename(path) or path
    is_dir = os.path.isdir(path)

    node: dict = {
        "name": name,
        "path": path,
        "type": "dir" if is_dir else "file",
        "status": statuses.get(path),
        "children": [],
    }

    if not is_dir or depth <= 0:
        return node

    try:
        entries = sorted(
            os.scandir(path),
            key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower()),
        )
    except PermissionError:
        return node

    for entry in entries:
        if entry.name.startswith("."):
            continue
        node["children"].append(_build_node(entry.path, depth - 1, statuses))

    return node
