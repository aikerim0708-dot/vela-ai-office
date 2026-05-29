"""
SQLite БД через SQLModel. Сущности минимальные — расширим в Stage 3 курса.

Путь к БД настраивается через env-переменную VELA_DB_PATH.
По умолчанию: <project>/data/office.db
"""
from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session


_default_db_path = Path(__file__).parent.parent / "data" / "office.db"
DB_PATH = Path(os.environ.get("VELA_DB_PATH", _default_db_path))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


class TaskRun(SQLModel, table=True):
    """Запуск агента: один промпт → один результат."""

    id: Optional[int] = Field(default=None, primary_key=True)
    agent_slug: str = Field(index=True)
    prompt: str
    output: str
    status: str  # queued | running | succeeded | failed
    is_mock: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
