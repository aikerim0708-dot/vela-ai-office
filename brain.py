"""
Brain VELA — общая память команды.

Это не агент, а БАЗА ЗНАНИЙ. Все агенты читают и пишут.

Сущности:
- Hypothesis  — гипотеза (метрика + срок + критерий + результат)
- ClusterBaseline — нормы по кластерам (CTR/CR/EPC, обновляет Лео)
- BidHistory — история ставок (Лео)
- FinanceBaseline — финансовые baselines (Зара, раз в неделю)
- Event — событие компании (просадка, рост, праздник) — Макс
- MarketingTest — A/B и контентные тесты (Ева)
- ChatPost — пост в общем чате AI Office
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Session, select

from db import engine


class Hypothesis(SQLModel, table=True):
    """Гипотеза: что меняем + ожидаемый результат + факт после срока."""

    id: Optional[int] = Field(default=None, primary_key=True)
    author_slug: str = Field(index=True)         # автор: leo, anna, eva, zara
    title: str
    action: str                                   # что меняем
    metric: str                                   # на какую метрику смотрим
    target: str                                   # критерий успеха
    deadline: Optional[str] = None                # дата проверки
    fallback: str                                 # что делаем если не зашло
    status: str = "open"                          # open | success | fail | cancelled
    result: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClusterBaseline(SQLModel, table=True):
    """Нормы по кластеру: усреднённые CTR/CR/EPC за 7/14/30 дней."""

    id: Optional[int] = Field(default=None, primary_key=True)
    cluster: str = Field(index=True)
    category: str                                # razors | lashes
    ctr_7d: Optional[float] = None
    cr_7d: Optional[float] = None
    epc_7d: Optional[float] = None
    ctr_30d: Optional[float] = None
    cr_30d: Optional[float] = None
    epc_30d: Optional[float] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = "leo"


class BidHistory(SQLModel, table=True):
    """История ставок: что было, что стало, эффект."""

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: str = Field(index=True)          # 29230612 / 32284868
    cluster: str = Field(index=True)
    old_bid: float
    new_bid: float
    reason: str
    expected_drr_delta: Optional[float] = None
    actual_drr_after_7d: Optional[float] = None
    decision_by: str = "leo"
    approved_by: str = "aikerim"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FinanceBaseline(SQLModel, table=True):
    """Финансовые baselines обновляются Зарой раз в неделю."""

    id: Optional[int] = Field(default=None, primary_key=True)
    week: str = Field(index=True)                 # ISO week, например 2026-W22
    revenue_avg: float
    profit_per_unit_avg: float
    margin_pct: float
    cac_razors: Optional[float] = None
    cac_lashes: Optional[float] = None
    drr_target: float = 17.0
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Event(SQLModel, table=True):
    """События компании: просадка, рост, праздник, баг WB."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(index=True)
    kind: str                                     # drop | growth | holiday | wb_issue | external
    title: str
    description: str
    impact_on_orders: Optional[str] = None        # e.g. "-18% за день"
    created_by: str = "max"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MarketingTest(SQLModel, table=True):
    """A/B и контентные тесты Евы."""

    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(index=True)
    hypothesis: str
    variant_a: str
    variant_b: str
    metric: str                                   # CR / CTR / средний чек
    deadline: Optional[str] = None
    status: str = "running"                       # running | winner_a | winner_b | inconclusive
    result_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatPost(SQLModel, table=True):
    """Сообщение в общем чате AI Office. Агенты постят сюда отчёты,
    Айкерим может читать ленту."""

    id: Optional[int] = Field(default=None, primary_key=True)
    author_slug: str = Field(index=True)          # max | leo | anna | zara | eva | aikerim
    kind: str = "report"                          # report | standup | alert | handoff | question | message
    channel: str = Field(default="group", index=True)  # group | max_dm
    title: str
    body: str
    related_task_id: Optional[int] = None         # связь с TaskRun
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# API над Brain VELA
# ---------------------------------------------------------------------------


def init_brain():
    SQLModel.metadata.create_all(engine)
    # Лёгкая миграция: добавляем колонку channel в существующую таблицу chatpost
    from sqlalchemy import text
    with Session(engine) as s:
        cols = [r[1] for r in s.exec(text("PRAGMA table_info(chatpost)")).all()]
        if "channel" not in cols:
            s.exec(text("ALTER TABLE chatpost ADD COLUMN channel VARCHAR DEFAULT 'group'"))
            s.commit()


def post_to_chat(author_slug: str, title: str, body: str, kind: str = "report",
                 task_id: Optional[int] = None, channel: str = "group") -> ChatPost:
    """Любой агент или Айкерим могут запостить в чат (группа или личка с Максом)."""
    with Session(engine) as s:
        post = ChatPost(
            author_slug=author_slug,
            kind=kind,
            channel=channel,
            title=title,
            body=body,
            related_task_id=task_id,
        )
        s.add(post)
        s.commit()
        s.refresh(post)
        return post


def list_chat(limit: int = 50, channel: Optional[str] = None) -> list[ChatPost]:
    with Session(engine) as s:
        stmt = select(ChatPost).order_by(ChatPost.created_at.desc()).limit(limit)
        if channel:
            stmt = stmt.where(ChatPost.channel == channel)
        return list(s.exec(stmt).all())


def max_dm_history(limit: int = 12) -> list[dict]:
    """История личной переписки с Максом для памяти COO.

    Возвращает список {role, content} в хронологическом порядке (старые→новые),
    готовый к подмешиванию в messages Claude. aikerim→user, max→assistant.
    """
    with Session(engine) as s:
        stmt = (select(ChatPost)
                .where(ChatPost.channel == "max_dm")
                .order_by(ChatPost.created_at.desc())
                .limit(limit))
        posts = list(s.exec(stmt).all())
    posts.reverse()  # хронология
    history = []
    for p in posts:
        role = "user" if p.author_slug == "aikerim" else "assistant"
        history.append({"role": role, "content": p.body})
    return history


def list_hypotheses(status: Optional[str] = None, limit: int = 100) -> list[Hypothesis]:
    with Session(engine) as s:
        stmt = select(Hypothesis).order_by(Hypothesis.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Hypothesis.status == status)
        return list(s.exec(stmt).all())


def decide_hypothesis(hyp_id: int, decision: str) -> Optional[Hypothesis]:
    """Айкерим принимает решение по гипотезе с главной страницы.

    decision='accepted' → запускаем (status=running), decision='rejected' → откладываем
    (status=cancelled). В обоих случаях гипотеза уходит из очереди «Ждут решения».
    """
    new_status = "running" if decision == "accepted" else "cancelled"
    note = "✅ одобрено Айкерим" if decision == "accepted" else "✕ отложено Айкерим"
    with Session(engine) as s:
        h = s.get(Hypothesis, hyp_id)
        if not h:
            return None
        h.status = new_status
        h.result = note
        s.add(h)
        s.commit()
        s.refresh(h)
        return h


def list_events(limit: int = 50) -> list[Event]:
    with Session(engine) as s:
        stmt = select(Event).order_by(Event.created_at.desc()).limit(limit)
        return list(s.exec(stmt).all())


def get_brain_summary() -> str:
    """Короткая сводка Brain VELA для system-промпта агента."""
    with Session(engine) as s:
        open_hypotheses = s.exec(
            select(Hypothesis).where(Hypothesis.status == "open").limit(5)
        ).all()
        recent_events = s.exec(
            select(Event).order_by(Event.created_at.desc()).limit(3)
        ).all()
        recent_baselines = s.exec(
            select(FinanceBaseline).order_by(FinanceBaseline.created_at.desc()).limit(1)
        ).all()

    parts = []
    if open_hypotheses:
        parts.append("Открытые гипотезы команды:")
        for h in open_hypotheses:
            parts.append(f"  - [{h.author_slug}] {h.title} — метрика {h.metric}, цель {h.target}, deadline {h.deadline or '?'}")

    if recent_events:
        parts.append("\nПоследние события компании:")
        for e in recent_events:
            parts.append(f"  - {e.date} ({e.kind}): {e.title}")

    if recent_baselines:
        b = recent_baselines[0]
        parts.append(f"\nФинансы (неделя {b.week}): выручка ~{b.revenue_avg:.0f}₽/день, маржа {b.margin_pct:.1f}%, цель ДРР {b.drr_target}%")

    if not parts:
        return "Brain VELA пока пуст — это начало работы команды."

    return "\n".join(parts)
