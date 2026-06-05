from __future__ import annotations

import json
from datetime import datetime

from memo.db.models import Chat, Message
from memo.db.session import SessionLocal


def create_chat(model: str, context_type: str = "none", context_paths: list[str] | None = None, include_subfolders: bool = False) -> dict:
    with SessionLocal() as db:
        chat = Chat(
            title="Новый чат",
            model=model,
            context_type=context_type,
            context_paths=json.dumps(context_paths or []),
            include_subfolders=include_subfolders,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return _chat_to_dict(chat)


def list_chats() -> list[dict]:
    with SessionLocal() as db:
        chats = db.query(Chat).order_by(Chat.updated_at.desc()).all()
        return [_chat_to_dict(c) for c in chats]


def get_chat(chat_id: int) -> dict | None:
    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        return _chat_to_dict(chat) if chat else None


def update_chat(chat_id: int, **kwargs) -> dict | None:
    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            return None
        for key, val in kwargs.items():
            if key == "context_paths" and isinstance(val, list):
                val = json.dumps(val)
            setattr(chat, key, val)
        chat.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(chat)
        return _chat_to_dict(chat)


def delete_chat(chat_id: int) -> bool:
    with SessionLocal() as db:
        chat = db.query(Chat).filter(Chat.id == chat_id).first()
        if not chat:
            return False
        db.query(Message).filter(Message.chat_id == chat_id).delete()
        db.delete(chat)
        db.commit()
        return True


def list_messages(chat_id: int) -> list[dict]:
    with SessionLocal() as db:
        msgs = db.query(Message).filter(Message.chat_id == chat_id).order_by(Message.created_at).all()
        return [_msg_to_dict(m) for m in msgs]


def add_message(chat_id: int, role: str, content: str, sources: list[str] | None = None) -> dict:
    with SessionLocal() as db:
        msg = Message(
            chat_id=chat_id,
            role=role,
            content=content,
            sources=json.dumps(sources or []),
        )
        db.add(msg)
        db.query(Chat).filter(Chat.id == chat_id).update({"updated_at": datetime.utcnow()})
        db.commit()
        db.refresh(msg)
        return _msg_to_dict(msg)


def set_chat_title_from_question(chat_id: int, question: str) -> None:
    title = question[:60].strip()
    if len(question) > 60:
        title += "…"
    with SessionLocal() as db:
        db.query(Chat).filter(Chat.id == chat_id).update({"title": title, "updated_at": datetime.utcnow()})
        db.commit()


def _chat_to_dict(chat: Chat) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "model": chat.model,
        "context_type": chat.context_type,
        "context_paths": json.loads(chat.context_paths) if chat.context_paths else [],
        "include_subfolders": chat.include_subfolders,
        "created_at": chat.created_at.isoformat() if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


def _msg_to_dict(msg: Message) -> dict:
    return {
        "id": msg.id,
        "chat_id": msg.chat_id,
        "role": msg.role,
        "content": msg.content,
        "sources": json.loads(msg.sources) if msg.sources else [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
