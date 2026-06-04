from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text
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
    indexed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    title = Column(String(256), nullable=False, default="New Chat")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, nullable=False, index=True)
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
