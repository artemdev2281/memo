from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class IndexState(Base):
    __tablename__ = "index_state"

    id = Column(Integer, primary_key=True)
    file_path = Column(String, unique=True, nullable=False, index=True)
    file_hash = Column(String(64), nullable=False, default="")
    status = Column(String(16), nullable=False, default="indexed")
    error_msg = Column(Text, nullable=True)
    indexed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False, default="New Chat")
    model = Column(String(128), nullable=False, default="")
    context_type = Column(String(16), nullable=False, default="none")
    context_paths = Column(Text, nullable=True)
    include_subfolders = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)
    thinking = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
