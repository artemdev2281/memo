import os
import shutil

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


def save_document(folder: str, filename: str, content: str) -> str:
    """Write content to folder/filename. Raises ValueError on invalid input or name collision."""
    if not filename:
        raise ValueError("Filename must not be empty")
    if "/" in filename or "\\" in filename or os.sep in filename:
        raise ValueError(f"Invalid filename (contains path separator): {filename!r}")
    if ".." in filename:
        raise ValueError(f"Invalid filename (contains '..'): {filename!r}")

    abs_folder = os.path.abspath(folder)
    if not os.path.isdir(abs_folder):
        raise ValueError(f"Not a directory: {folder!r}")

    dest = os.path.join(abs_folder, filename)
    if os.path.exists(dest):
        raise ValueError(f"File already exists: {filename!r}")

    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return dest


def apply_organization(base_folder: str, plan: list[dict]) -> dict:
    """
    Move files according to plan = [{"folder_name": str, "files": [abs paths]}].
    Rolls back all moves on any error. Returns {"folders_created": int, "files_moved": int}.
    """
    abs_base = os.path.abspath(base_folder)
    moves_done: list[tuple[str, str]] = []
    dirs_created: list[str] = []

    try:
        for cluster in plan:
            folder_name = cluster.get("folder_name", "")
            files = cluster.get("files", [])
            if not folder_name or not files:
                continue

            if "/" in folder_name or "\\" in folder_name or ".." in folder_name:
                raise ValueError(f"Invalid folder_name (path traversal): {folder_name!r}")

            dest_dir = os.path.join(abs_base, folder_name)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)
                dirs_created.append(dest_dir)

            for src_path in files:
                abs_src = os.path.abspath(src_path)
                dest_path = os.path.join(dest_dir, os.path.basename(abs_src))
                abs_dest = os.path.abspath(dest_path)
                if abs_src == abs_dest:
                    continue
                if not os.path.isfile(abs_src):
                    continue
                shutil.move(abs_src, abs_dest)
                moves_done.append((abs_src, abs_dest))

    except Exception as e:
        for src, dest in reversed(moves_done):
            try:
                shutil.move(dest, src)
            except Exception:
                pass
        for d in reversed(dirs_created):
            try:
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
            except Exception:
                pass
        raise ValueError(f"Ошибка применения организации: {e}")

    return {
        "folders_created": len(dirs_created),
        "files_moved": len(moves_done),
    }
