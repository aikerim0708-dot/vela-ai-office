"""
Knowledge Inbox VELA — папка для новых знаний от Айкерим.

Сюда падают:
- Новости WB (изменение комиссии, новые правила, обновления API)
- Скрины/факты о конкурентах
- Заметки "поменяла цену с X на Y", "запустила новую кампанию"
- Письма от поставщика (изменение цен/MOQ/lead-time)
- Скрины отзывов, которые надо разобрать командно

Что делает Макс при запросе /api/inbox/process:
1. Читает все pending items
2. Классифицирует (kind: wb_news | competitor | price_change | supply | review | other)
3. Записывает в Brain VELA (Event или KnowledgeItem)
4. Если требуется — триггерит реактивную цепочку (например, price_change → Зара пересчитывает)
5. Перемещает файл в processed/ + помечает item.status = processed
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Session, select
from db import engine


INBOX_DIR = Path(__file__).parent.parent / "data" / "inbox"
PROCESSED_DIR = INBOX_DIR / "processed"
INBOX_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Модель: запись в Inbox
# ---------------------------------------------------------------------------


class InboxItem(SQLModel, table=True):
    """Любая входящая знание/заметка от Айкерим.

    Может быть:
    - текстовой ("снизила цену бритвы до 890")
    - или указывать на файл в data/inbox/ (скрин, pdf, xlsx)
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    note: str                                          # текст заметки от Айкерим
    filename: Optional[str] = None                     # если есть прикреплённый файл
    kind: str = "unknown"                              # wb_news | competitor | price_change |
                                                       # supply | review | other | unknown
    status: str = "pending"                            # pending | processed | failed
    triggers_chain: Optional[str] = None               # какая реактивная цепочка запустилась
    processed_summary: Optional[str] = None            # что Макс записал в Brain
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None


class KnowledgeItem(SQLModel, table=True):
    """Структурированное знание после обработки Inbox.

    Это и есть «папка где мозг хранит свежие новости WB и факты».
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)                      # wb_rule | competitor | price | supply | other
    title: str
    body: str                                          # сжатое описание (4-8 предложений макс)
    source_inbox_id: Optional[int] = None              # ссылка на исходный inbox item
    relevance: str = "active"                          # active | archived
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def init_inbox():
    SQLModel.metadata.create_all(engine)


def add_item(note: str, filename: Optional[str] = None) -> InboxItem:
    """Добавить запись в inbox (текст + опционально файл)."""
    with Session(engine) as s:
        item = InboxItem(note=note, filename=filename, status="pending")
        s.add(item)
        s.commit()
        s.refresh(item)
        return item


def list_pending(limit: int = 50) -> list[InboxItem]:
    with Session(engine) as s:
        stmt = (
            select(InboxItem)
            .where(InboxItem.status == "pending")
            .order_by(InboxItem.created_at.asc())
            .limit(limit)
        )
        return list(s.exec(stmt).all())


def list_all(limit: int = 50) -> list[InboxItem]:
    with Session(engine) as s:
        stmt = select(InboxItem).order_by(InboxItem.created_at.desc()).limit(limit)
        return list(s.exec(stmt).all())


def mark_processed(item_id: int, summary: str, kind: str,
                   triggers_chain: Optional[str] = None) -> Optional[InboxItem]:
    with Session(engine) as s:
        item = s.get(InboxItem, item_id)
        if not item:
            return None
        item.status = "processed"
        item.processed_summary = summary
        item.kind = kind
        item.triggers_chain = triggers_chain
        item.processed_at = datetime.utcnow()
        s.add(item)
        s.commit()
        s.refresh(item)
        # переносим файл в processed/
        if item.filename:
            src = INBOX_DIR / item.filename
            if src.exists():
                dest = PROCESSED_DIR / item.filename
                try:
                    src.rename(dest)
                except Exception:
                    pass
        return item


def add_knowledge(kind: str, title: str, body: str, source_inbox_id: int) -> KnowledgeItem:
    with Session(engine) as s:
        item = KnowledgeItem(
            kind=kind, title=title, body=body, source_inbox_id=source_inbox_id
        )
        s.add(item)
        s.commit()
        s.refresh(item)
        return item


def list_knowledge(kind: Optional[str] = None, limit: int = 30) -> list[KnowledgeItem]:
    with Session(engine) as s:
        stmt = select(KnowledgeItem).where(KnowledgeItem.relevance == "active")
        if kind:
            stmt = stmt.where(KnowledgeItem.kind == kind)
        stmt = stmt.order_by(KnowledgeItem.created_at.desc()).limit(limit)
        return list(s.exec(stmt).all())


def knowledge_summary_for_agents(limit: int = 12) -> str:
    """Краткая сводка KnowledgeItem для system-промптов агентов."""
    items = list_knowledge(limit=limit)
    if not items:
        return ""
    parts = ["Свежие знания команды (из Inbox Айкерим):"]
    for it in items:
        date = it.created_at.strftime("%Y-%m-%d")
        body_short = it.body[:240] + ("…" if len(it.body) > 240 else "")
        parts.append(f"  - [{it.kind} · {date}] {it.title}\n    {body_short}")
    return "\n".join(parts)
