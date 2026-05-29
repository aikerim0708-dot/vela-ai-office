"""
VELA AI Office — FastAPI backend.

Запуск:
    cd backend
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000

Env переменные:
    VELA_PROVIDER=mock|claude   — какой провайдер агентов (по умолчанию mock)
    ANTHROPIC_API_KEY=sk-ant-…   — нужен если VELA_PROVIDER=claude
    VELA_MODEL=claude-sonnet-4-5 — модель Claude (по умолчанию)
    VELA_DB_PATH=/path/office.db  — путь к SQLite (по умолчанию data/office.db)

Endpoints:
    GET  /                       — frontend (index.html)
    GET  /agent/{slug}           — frontend agent page
    GET  /api/health             — healthcheck
    GET  /api/agents             — список агентов VELA
    GET  /api/agents/{slug}      — карточка агента + шаблоны
    POST /api/tasks              — запустить задачу через агента
    GET  /api/tasks              — история задач
    GET  /api/tasks/{id}         — детали задачи
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session, select

# Загрузить .env до импорта agents (там читаются env-переменные)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from agents import create_provider, VELA_AGENTS, ClaudeAgentProvider
from db import TaskRun, init_db, get_session
import brain
import inbox
import wb_api


# ---------- Provider switching через env VELA_PROVIDER ----------
agent_provider = create_provider()


# ---------- App ----------
app = FastAPI(
    title="VELA AI Office",
    description="Telegram Mini App для управления агентами VELA (Wildberries бизнес)",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    brain.init_brain()
    inbox.init_inbox()


# ---------- Frontend ----------
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/")
def root():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/agent/{slug}")
def agent_page(slug: str):
    if not agent_provider.get_agent(slug):
        raise HTTPException(status_code=404, detail="Агент не найден")
    return FileResponse(FRONTEND_DIR / "agent.html")


@app.get("/tasks")
def tasks_page():
    return FileResponse(FRONTEND_DIR / "tasks.html")


@app.get("/more")
def more_page():
    return FileResponse(FRONTEND_DIR / "more.html")


@app.get("/chat")
def chat_page():
    return FileResponse(FRONTEND_DIR / "chat.html")


@app.get("/brain")
def brain_page():
    return FileResponse(FRONTEND_DIR / "brain.html")


@app.get("/reports")
def reports_page():
    return FileResponse(FRONTEND_DIR / "reports.html")


# Статика (style.css, app.js)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ---------- API ----------
@app.get("/api/health")
def health():
    import os
    return {
        "status": "ok",
        "time": datetime.utcnow().isoformat() + "Z",
        "provider": os.environ.get("VELA_PROVIDER", "mock"),
        "agents_count": len(VELA_AGENTS),
    }


@app.get("/api/agents")
def list_agents():
    return {"agents": agent_provider.list_agents()}


@app.get("/api/agents/{slug}")
def get_agent(slug: str):
    agent = agent_provider.get_agent(slug)
    if not agent:
        raise HTTPException(status_code=404, detail="Агент не найден")
    return agent


class TaskCreateRequest(BaseModel):
    agent_slug: str
    prompt: str


@app.post("/api/tasks")
def create_task(req: TaskCreateRequest, session: Session = Depends(get_session)):
    # Передаём агенту контекст Brain VELA + свежие данные WB + knowledge inbox
    brain_ctx = brain.get_brain_summary()
    knowledge_block = inbox.knowledge_summary_for_agents()
    if knowledge_block:
        brain_ctx = f"{brain_ctx}\n\n{knowledge_block}" if brain_ctx else knowledge_block
    if isinstance(agent_provider, ClaudeAgentProvider):
        try:
            snap = wb_api.fetch_snapshot()
            wb_block = wb_api.snapshot_for_agent_context(snap)
            brain_ctx = f"{brain_ctx}\n\n{wb_block}" if brain_ctx else wb_block
        except Exception as e:
            brain_ctx = (brain_ctx or "") + f"\n\n⚠️ WB API недоступен: {e}"
        result = agent_provider.run_task(req.agent_slug, req.prompt, brain_context=brain_ctx)
    else:
        result = agent_provider.run_task(req.agent_slug, req.prompt)

    if result["status"] == "failed" and "не найден" in result.get("output", ""):
        raise HTTPException(status_code=400, detail=result["output"])

    task = TaskRun(
        agent_slug=req.agent_slug,
        prompt=req.prompt,
        output=result["output"],
        status=result["status"],
        is_mock=result.get("is_mock", True),
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # Постим в общий чат AI Office
    from agents import find_agent
    agent = find_agent(req.agent_slug)
    if agent:
        title_preview = req.prompt[:80] + ("…" if len(req.prompt) > 80 else "")
        brain.post_to_chat(
            author_slug=req.agent_slug,
            title=f"закрыл #{task.id}: {title_preview}",
            body=result["output"][:500] + ("…" if len(result["output"]) > 500 else ""),
            kind="alert" if result["status"] == "failed" else "report",
            task_id=task.id,
        )

    return {
        "id": task.id,
        "agent_slug": task.agent_slug,
        "status": task.status,
        "output": task.output,
        "is_mock": task.is_mock,
        "created_at": task.created_at.isoformat() + "Z",
    }


# ---------- WB API: реальные данные с Wildberries ----------
@app.get("/api/wb/snapshot")
def wb_snapshot():
    """Свежий snapshot WB: вчерашние заказы/продажи, остатки, кампании, отзывы.
    Кешируется на 5 минут (statistics-api имеет лимит 1 req/min)."""
    return wb_api.fetch_snapshot()


@app.post("/api/wb/cache/clear")
def wb_clear_cache():
    """Сбросить кеш WB snapshot (когда хочешь обновить раньше 5 минут)."""
    wb_api.clear_cache()
    return {"status": "ok", "message": "Кеш WB snapshot очищен"}


@app.get("/api/digest/morning")
def morning_digest():
    """Утренний дайджест VELA — компактные KPI для главной страницы Mini App.

    Заменяет захардкоженный блок "Сервер 6% CPU…" на реальные цифры:
    заказы вчера, выручка, ДРР по обеим кампаниям, OOS-флаги, неотвеченные отзывы,
    pending inbox, открытые гипотезы.
    """
    try:
        snap = wb_api.fetch_snapshot()
    except Exception as e:
        snap = {"error": str(e)}

    orders = snap.get("orders", {}) if isinstance(snap, dict) else {}
    sales = snap.get("sales", {}) if isinstance(snap, dict) else {}
    stocks = snap.get("stocks", {}) if isinstance(snap, dict) else {}
    camps = snap.get("campaigns", {}) if isinstance(snap, dict) else {}
    fb = snap.get("feedbacks", {}) if isinstance(snap, dict) else {}

    razors = camps.get("razors_29230612", {}) if isinstance(camps, dict) else {}
    lashes = camps.get("lashes_32284868", {}) if isinstance(camps, dict) else {}

    pending_inbox = len(inbox.list_pending())
    open_hyps = len(brain.list_hypotheses(status="open"))

    # Светофор: какой статус общий
    flags = []
    if isinstance(orders, dict) and orders.get("total_orders") is not None:
        if orders.get("total_orders") == 0:
            flags.append({"level": "red", "text": "Заказов вчера: 0"})
    if isinstance(razors, dict) and razors.get("drr_pct") is not None:
        if razors["drr_pct"] > 25:
            flags.append({"level": "yellow", "text": f"ДРР бритвы {razors['drr_pct']}% (выше 25%)"})
    if isinstance(lashes, dict) and lashes.get("drr_pct") is not None:
        if lashes["drr_pct"] > 25:
            flags.append({"level": "yellow", "text": f"ДРР ресницы {lashes['drr_pct']}% (выше 25%)"})
    if isinstance(fb, dict) and fb.get("critical_count", 0) > 5:
        flags.append({"level": "yellow", "text": f"Критичных отзывов: {fb['critical_count']}"})
    if pending_inbox > 0:
        flags.append({"level": "blue", "text": f"В inbox ждут обработки: {pending_inbox}"})

    overall = "green" if not flags else ("red" if any(f["level"] == "red" for f in flags) else "yellow")

    return {
        "overall": overall,
        "yesterday": snap.get("yesterday"),
        "orders_count": orders.get("total_orders") if isinstance(orders, dict) else None,
        "revenue_rub": orders.get("revenue_orders_total") if isinstance(orders, dict) else None,
        "sales_count": sales.get("sales_count") if isinstance(sales, dict) else None,
        "sales_for_pay_rub": sales.get("total_for_pay") if isinstance(sales, dict) else None,
        "stocks_units": stocks.get("total_units") if isinstance(stocks, dict) else None,
        "razors": {
            "drr_pct": razors.get("drr_pct"),
            "spend_rub": razors.get("spend_rub"),
            "orders": razors.get("orders"),
        } if isinstance(razors, dict) else {},
        "lashes": {
            "drr_pct": lashes.get("drr_pct"),
            "spend_rub": lashes.get("spend_rub"),
            "orders": lashes.get("orders"),
        } if isinstance(lashes, dict) else {},
        "feedbacks_unanswered": fb.get("total") if isinstance(fb, dict) else None,
        "feedbacks_critical": fb.get("critical_count") if isinstance(fb, dict) else None,
        "pending_inbox": pending_inbox,
        "open_hypotheses": open_hyps,
        "flags": flags,
    }


# ---------- Orchestration: Айкерим → Макс → команда → сводка ----------
class GoalRequest(BaseModel):
    goal: str
    include_wb_data: bool = True  # автоматически тянуть свежий snapshot WB


@app.post("/api/goal")
def post_goal(req: GoalRequest, session: Session = Depends(get_session)):
    """Айкерим ставит цель. Макс делегирует команде, собирает финальный ответ.

    Работает только если VELA_PROVIDER=claude (нужны 2 этапа Claude API).
    Если include_wb_data=True — автоматически тянет snapshot WB и передаёт
    как контекст всем агентам.
    """
    if not isinstance(agent_provider, ClaudeAgentProvider):
        raise HTTPException(
            status_code=400,
            detail="Orchestration требует VELA_PROVIDER=claude в .env"
        )

    brain_ctx = brain.get_brain_summary()

    # Подмешиваем свежие знания из Inbox (новости WB, конкуренты, изменения цен)
    knowledge_block = inbox.knowledge_summary_for_agents()
    if knowledge_block:
        brain_ctx = f"{brain_ctx}\n\n{knowledge_block}" if brain_ctx else knowledge_block

    # Дополняем контекст реальными данными WB
    if req.include_wb_data:
        try:
            snap = wb_api.fetch_snapshot()
            wb_block = wb_api.snapshot_for_agent_context(snap)
            brain_ctx = f"{brain_ctx}\n\n{wb_block}" if brain_ctx else wb_block
        except Exception as e:
            brain_ctx = (brain_ctx or "") + f"\n\n⚠️ WB API недоступен: {e}"

    result = agent_provider.orchestrate_goal(req.goal, brain_context=brain_ctx)

    # Сохраняем итог как TaskRun от Макса
    task = TaskRun(
        agent_slug="max",
        prompt=f"[GOAL] {req.goal}",
        output=result["final_summary"],
        status="succeeded",
        is_mock=False,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # Постим каждый ответ агента в чат + финальный пост Макса
    for r in result.get("agent_results", []):
        brain.post_to_chat(
            author_slug=r["agent"],
            title=f"закрыл задачу от Макса: {r['task'][:80]}",
            body=r["output"][:500] + ("…" if len(r["output"]) > 500 else ""),
            kind="report",
            task_id=task.id,
        )
    brain.post_to_chat(
        author_slug="max",
        title=f"свод по цели «{req.goal[:60]}»",
        body=result["final_summary"][:800],
        kind="standup",
        task_id=task.id,
    )

    return {
        "task_id": task.id,
        "goal": req.goal,
        "plan": result.get("plan"),
        "delegations": result.get("delegations", []),
        "needs_data_from_aikerim": result.get("needs_data_from_aikerim", []),
        "agent_results": result.get("agent_results", []),
        "final_summary": result["final_summary"],
        "fallback": result.get("fallback", False),
    }


# ---------- Brain VELA + Chat API ----------
def _serialize_post(p):
    from agents import find_agent
    if p.author_slug == "aikerim":
        name, avatar = "Айкерим", "🌙"
    else:
        a = find_agent(p.author_slug) or {}
        name = a.get("name", p.author_slug)
        avatar = a.get("avatar_emoji", "🤖")
    return {
        "id": p.id,
        "author_slug": p.author_slug,
        "author_name": name,
        "author_avatar": avatar,
        "is_me": p.author_slug == "aikerim",
        "kind": p.kind,
        "channel": getattr(p, "channel", "group"),
        "title": p.title,
        "body": p.body,
        "related_task_id": p.related_task_id,
        "created_at": p.created_at.isoformat() + "Z",
    }


@app.get("/api/chat")
def get_chat(limit: int = 50, channel: str = ""):
    posts = brain.list_chat(limit=limit, channel=channel or None)
    return {"posts": [_serialize_post(p) for p in posts]}


# Карта @упоминаний → slug агента
_MENTION_MAP = {
    "макс": "max", "max": "max",
    "лео": "leo", "leo": "leo",
    "анна": "anna", "anna": "anna", "аня": "anna",
    "зара": "zara", "zara": "zara",
    "ева": "eva", "eva": "eva",
    "все": "all", "команда": "all",
}


def _detect_mention(text: str) -> Optional[str]:
    """Ищет @упоминание агента в начале/любом месте сообщения. Возвращает slug или None."""
    import re
    for m in re.finditer(r"@([A-Za-zА-Яа-яЁё]+)", text):
        slug = _MENTION_MAP.get(m.group(1).lower())
        if slug:
            return slug
    return None


def _build_brain_ctx(include_wb: bool = True) -> str:
    brain_ctx = brain.get_brain_summary()
    knowledge_block = inbox.knowledge_summary_for_agents()
    if knowledge_block:
        brain_ctx = f"{brain_ctx}\n\n{knowledge_block}" if brain_ctx else knowledge_block
    if include_wb and isinstance(agent_provider, ClaudeAgentProvider):
        try:
            snap = wb_api.fetch_snapshot()
            wb_block = wb_api.snapshot_for_agent_context(snap)
            brain_ctx = f"{brain_ctx}\n\n{wb_block}" if brain_ctx else wb_block
        except Exception as e:
            brain_ctx = (brain_ctx or "") + f"\n\n⚠️ WB API недоступен: {e}"
    return brain_ctx


class ChatSendRequest(BaseModel):
    text: str


@app.post("/api/chat/send")
def chat_send_group(req: ChatSendRequest, session: Session = Depends(get_session)):
    """Групповой чат команды. Сохраняет сообщение Айкерим и запускает агентов.

    @упоминание (@Лео, @Зара) → отвечает один агент (дёшево, быстро).
    Без @упоминания → Макс созывает команду (оркестрация, дольше и дороже).
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    if not isinstance(agent_provider, ClaudeAgentProvider):
        raise HTTPException(status_code=400, detail="Чат требует VELA_PROVIDER=claude")

    # 1. Сохраняем реплику Айкерим
    brain.post_to_chat("aikerim", title="", body=text, kind="message", channel="group")

    mention = _detect_mention(text)
    brain_ctx = _build_brain_ctx(include_wb=True)
    replies = []

    if mention and mention != "all":
        # Один агент отвечает
        result = agent_provider.run_task(mention, text, brain_context=brain_ctx)
        brain.post_to_chat(mention, title="", body=result["output"], kind="message", channel="group")
        replies.append({"agent": mention, "output": result["output"]})
    else:
        # Макс созывает команду (оркестрация)
        result = agent_provider.orchestrate_goal(text, brain_context=brain_ctx)
        for r in result.get("agent_results", []):
            brain.post_to_chat(r["agent"], title="", body=r["output"], kind="message", channel="group")
            replies.append({"agent": r["agent"], "output": r["output"]})
        brain.post_to_chat("max", title="", body=result["final_summary"], kind="message", channel="group")
        replies.append({"agent": "max", "output": result["final_summary"]})

    return {"ok": True, "mention": mention, "replies": replies}


@app.post("/api/chat/max")
def chat_max_dm(req: ChatSendRequest, session: Session = Depends(get_session)):
    """Личная переписка с Максом (COO) — с памятью предыдущих реплик."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    if not isinstance(agent_provider, ClaudeAgentProvider):
        raise HTTPException(status_code=400, detail="Чат требует VELA_PROVIDER=claude")

    # 1. История ДО сохранения новой реплики (чтобы не задвоить)
    history = brain.max_dm_history(limit=12)

    # 2. Сохраняем реплику Айкерим
    brain.post_to_chat("aikerim", title="", body=text, kind="message", channel="max_dm")

    # 3. Макс отвечает как COO, помня контекст
    brain_ctx = _build_brain_ctx(include_wb=True)
    result = agent_provider.run_task("max", text, brain_context=brain_ctx, history=history)
    brain.post_to_chat("max", title="", body=result["output"], kind="message", channel="max_dm")

    return {"ok": True, "output": result["output"]}


@app.get("/api/brain/summary")
def brain_summary():
    return {"summary": brain.get_brain_summary()}


@app.get("/api/brain/hypotheses")
def list_hypotheses_api(status: str = ""):
    hyps = brain.list_hypotheses(status=status or None)
    return {
        "hypotheses": [
            {
                "id": h.id,
                "author_slug": h.author_slug,
                "title": h.title,
                "action": h.action,
                "metric": h.metric,
                "target": h.target,
                "deadline": h.deadline,
                "fallback": h.fallback,
                "status": h.status,
                "result": h.result,
                "created_at": h.created_at.isoformat() + "Z",
            }
            for h in hyps
        ]
    }


class HypothesisDecision(BaseModel):
    decision: str  # accepted | rejected


@app.post("/api/brain/hypotheses/{hyp_id}/decide")
def decide_hypothesis_api(hyp_id: int, req: HypothesisDecision):
    if req.decision not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="decision должен быть accepted или rejected")
    h = brain.decide_hypothesis(hyp_id, req.decision)
    if not h:
        raise HTTPException(status_code=404, detail="Гипотеза не найдена")
    return {"id": h.id, "status": h.status, "result": h.result}


@app.get("/api/brain/events")
def list_events_api():
    events = brain.list_events()
    return {
        "events": [
            {
                "id": e.id,
                "date": e.date,
                "kind": e.kind,
                "title": e.title,
                "description": e.description,
                "impact_on_orders": e.impact_on_orders,
                "created_by": e.created_by,
                "created_at": e.created_at.isoformat() + "Z",
            }
            for e in events
        ]
    }


@app.get("/api/tasks")
def list_tasks(limit: int = 20, session: Session = Depends(get_session)):
    stmt = select(TaskRun).order_by(TaskRun.created_at.desc()).limit(limit)
    tasks = session.exec(stmt).all()
    return {
        "tasks": [
            {
                "id": t.id,
                "agent_slug": t.agent_slug,
                "prompt": t.prompt[:120] + ("…" if len(t.prompt) > 120 else ""),
                "status": t.status,
                "is_mock": t.is_mock,
                "created_at": t.created_at.isoformat() + "Z",
            }
            for t in tasks
        ]
    }


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(TaskRun, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return {
        "id": task.id,
        "agent_slug": task.agent_slug,
        "prompt": task.prompt,
        "output": task.output,
        "status": task.status,
        "is_mock": task.is_mock,
        "created_at": task.created_at.isoformat() + "Z",
    }


# ---------- WB integration ----------
UPLOADS_DIR = Path(__file__).parent.parent / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/wb/health")
def wb_health():
    """Проверка живости WB API токена. Дёргает /adv/v1/promotion/count."""
    from wb_client import WBClient
    return WBClient().ping()


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Загрузка Excel/CSV для агентов. Файл попадает в data/uploads/.

    Агенты затем читают его инструментом read_uploaded_file."""
    allowed = {".xlsx", ".xls", ".xlsm", ".csv"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Поддерживаются только {sorted(allowed)}")

    # safe filename — только базовое имя
    safe_name = Path(file.filename).name
    dest = UPLOADS_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)
    return {
        "ok": True,
        "filename": safe_name,
        "size_kb": round(len(content) / 1024, 1),
        "saved_to": str(dest.relative_to(Path(__file__).parent.parent)),
    }


@app.get("/api/uploads")
def list_uploads():
    files = []
    for p in UPLOADS_DIR.iterdir():
        if p.is_file():
            files.append({
                "name": p.name,
                "size_kb": round(p.stat().st_size / 1024, 1),
                "modified_at": datetime.utcfromtimestamp(p.stat().st_mtime).isoformat() + "Z",
            })
    files.sort(key=lambda x: x["modified_at"], reverse=True)
    return {"files": files}


@app.delete("/api/uploads/{filename}")
def delete_upload(filename: str):
    safe_name = Path(filename).name
    target = UPLOADS_DIR / safe_name
    if target.exists() and target.is_file():
        target.unlink()
        return {"ok": True, "deleted": safe_name}
    raise HTTPException(status_code=404, detail="Файл не найден")


# ---------- Knowledge Inbox: входящие знания для мозга ----------
INBOX_DIR = Path(__file__).parent.parent / "data" / "inbox"


class InboxAddRequest(BaseModel):
    note: str
    filename: Optional[str] = None  # если файл уже загружен через /api/inbox/upload


@app.post("/api/inbox")
def add_inbox(req: InboxAddRequest):
    """Добавить запись в inbox мозга. Только текст (файл — через /api/inbox/upload)."""
    item = inbox.add_item(req.note, filename=req.filename)
    return {
        "id": item.id,
        "note": item.note,
        "filename": item.filename,
        "status": item.status,
        "created_at": item.created_at.isoformat() + "Z",
    }


@app.post("/api/inbox/upload")
async def upload_inbox_file(file: UploadFile = File(...), note: str = ""):
    """Загрузить файл в inbox + создать pending запись.

    Поддерживает картинки (скрины конкурентов), pdf (новости WB),
    xlsx/csv (выгрузки), txt.
    """
    allowed = {".png", ".jpg", ".jpeg", ".pdf", ".xlsx", ".xls", ".csv", ".xlsm", ".txt", ".md"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Поддерживаются: {sorted(allowed)}")

    safe_name = Path(file.filename).name
    dest = INBOX_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)
    item = inbox.add_item(note=note or f"Файл {safe_name}", filename=safe_name)
    return {
        "ok": True,
        "id": item.id,
        "filename": safe_name,
        "size_kb": round(len(content) / 1024, 1),
        "status": item.status,
    }


@app.get("/api/inbox")
def list_inbox(only_pending: bool = False):
    items = inbox.list_pending() if only_pending else inbox.list_all()
    return {
        "items": [
            {
                "id": i.id,
                "note": i.note,
                "filename": i.filename,
                "kind": i.kind,
                "status": i.status,
                "triggers_chain": i.triggers_chain,
                "processed_summary": i.processed_summary,
                "created_at": i.created_at.isoformat() + "Z",
                "processed_at": i.processed_at.isoformat() + "Z" if i.processed_at else None,
            }
            for i in items
        ]
    }


@app.get("/api/inbox/knowledge")
def list_knowledge(kind: str = ""):
    items = inbox.list_knowledge(kind=kind or None)
    return {
        "items": [
            {
                "id": i.id,
                "kind": i.kind,
                "title": i.title,
                "body": i.body,
                "source_inbox_id": i.source_inbox_id,
                "created_at": i.created_at.isoformat() + "Z",
            }
            for i in items
        ]
    }


@app.post("/api/inbox/process")
def process_inbox(session: Session = Depends(get_session)):
    """Макс читает все pending items, классифицирует, обновляет Brain.

    Триггерит реактивные цепочки для price_change и supply.
    Работает только с Claude провайдером.
    """
    if not isinstance(agent_provider, ClaudeAgentProvider):
        raise HTTPException(
            status_code=400,
            detail="Inbox processing требует VELA_PROVIDER=claude в .env"
        )

    pending = inbox.list_pending()
    if not pending:
        return {"processed": 0, "message": "Inbox пуст"}

    processed_summary = []
    triggered_chains = []

    for item in pending:
        # Промпт для Макса: классифицировать + извлечь knowledge + решить о цепочке
        max_prompt = f"""Айкерим положила в inbox запись:

NOTE: {item.note}
{f"FILE: data/inbox/{item.filename}" if item.filename else "(без файла)"}

Сделай 4 шага:

1. KIND — классифицируй:
   - wb_news (новости/правила WB, изменение комиссий, обновления API)
   - competitor (новости/факт о конкуренте)
   - price_change (Айкерим сменила цену SKU)
   - supply (новости поставщика, lead-time, MOQ, цены закупки)
   - review (отзыв клиента, требует разбора)
   - other

2. TITLE — короткий заголовок (≤ 80 символов)

3. BODY — сжатое описание для Brain VELA (4-8 предложений). Извлеки ключевые факты, цифры, даты.

4. REACTIVE_CHAIN — если запись требует немедленных действий команды, верни строку с slug агентов через запятую (например "zara,leo" для price_change). Если ничего не нужно делать — верни "none".

Ответь СТРОГО в JSON между маркерами:

<INBOX>
{{
  "kind": "wb_news|competitor|price_change|supply|review|other",
  "title": "короткий заголовок",
  "body": "сжатое описание для Brain",
  "reactive_chain": "none|slug1,slug2"
}}
</INBOX>
"""
        try:
            result = agent_provider.run_task("max", max_prompt)
        except Exception as e:
            processed_summary.append({"id": item.id, "error": str(e)})
            continue

        import re
        import json
        text = result.get("output", "")
        m = re.search(r"<INBOX>(.*?)</INBOX>", text, re.DOTALL)
        if not m:
            processed_summary.append({"id": item.id, "error": "Макс не вернул JSON"})
            continue
        try:
            parsed = json.loads(m.group(1).strip())
        except json.JSONDecodeError as e:
            processed_summary.append({"id": item.id, "error": f"JSON parse: {e}"})
            continue

        kind = parsed.get("kind", "other")
        title = parsed.get("title", item.note[:60])
        body = parsed.get("body", item.note)
        chain = parsed.get("reactive_chain", "none")

        # Сохраняем в Knowledge
        inbox.add_knowledge(kind=kind, title=title, body=body, source_inbox_id=item.id)

        # Пишем в общий чат
        brain.post_to_chat(
            author_slug="max",
            title=f"Inbox обработан: {title[:60]}",
            body=f"[{kind}] {body[:400]}",
            kind="report",
        )

        # Если требуется реактивная цепочка — триггерим
        triggered = None
        if chain and chain != "none":
            chain_slugs = [s.strip() for s in chain.split(",") if s.strip() in {"leo", "anna", "zara", "eva"}]
            if chain_slugs:
                chain_goal = (
                    f"Реактивная цепочка по новому знанию из Inbox [{kind}]: «{title}». "
                    f"Контекст: {body}. "
                    f"Делегируй: {', '.join(chain_slugs)} — каждый должен проверить свою зону и предложить действия."
                )
                triggered = chain_goal
                # Запускаем orchestration асинхронно? Пока — синхронно но компактно
                try:
                    chain_result = agent_provider.orchestrate_goal(chain_goal)
                    brain.post_to_chat(
                        author_slug="max",
                        title=f"Цепочка отработана: {title[:50]}",
                        body=chain_result.get("final_summary", "")[:600],
                        kind="standup",
                    )
                    triggered_chains.append({"item_id": item.id, "chain": chain})
                except Exception as e:
                    triggered_chains.append({"item_id": item.id, "chain": chain, "error": str(e)})

        inbox.mark_processed(
            item_id=item.id,
            summary=f"{kind}: {title}",
            kind=kind,
            triggers_chain=chain if chain != "none" else None,
        )
        processed_summary.append({
            "id": item.id,
            "kind": kind,
            "title": title,
            "triggered_chain": triggered is not None,
        })

    return {
        "processed": len(processed_summary),
        "items": processed_summary,
        "chains": triggered_chains,
    }


# ============================================================
# /api/reports/* — авто-генерация и просмотр отчётов VELA
# ============================================================
from reports import (
    generate_daily as _gen_daily,
    generate_weekly as _gen_weekly,
    generate_monthly as _gen_monthly,
    list_reports as _list_reports,
    read_report as _read_report,
    yesterday_iso as _yesterday_iso,
)


@app.get("/api/reports")
def api_reports_list():
    """Список всех сохранённых отчётов с метаданными."""
    return {"reports": _list_reports()}


@app.get("/api/reports/{filename}")
def api_reports_read(filename: str):
    """Читать конкретный отчёт по имени файла."""
    md = _read_report(filename)
    if md is None:
        raise HTTPException(404, f"Отчёт {filename} не найден")
    return {"filename": filename, "markdown": md}


class ReportGenerateRequest(BaseModel):
    type: str  # daily | weekly | monthly
    date: Optional[str] = None  # для daily YYYY-MM-DD, для weekly воскресенье, для monthly YYYY-MM


@app.post("/api/reports/generate")
def api_reports_generate(req: ReportGenerateRequest):
    """Триггер генерации отчёта вручную (или cron из VDS)."""
    try:
        if req.type == "daily":
            md, meta = _gen_daily(target_date=req.date)
        elif req.type == "weekly":
            md, meta = _gen_weekly(week_end_date=req.date)
        elif req.type == "monthly":
            md, meta = _gen_monthly(month=req.date)
        else:
            raise HTTPException(400, f"Неизвестный тип: {req.type}")
        return {"ok": True, "meta": meta, "markdown_first_500": md[:500]}
    except Exception as e:
        raise HTTPException(500, f"Ошибка генерации: {e}")


@app.get("/api/reports/latest/daily")
def api_reports_latest_daily():
    """Возвращает последний daily отчёт (за вчера). Если его нет — генерирует."""
    yesterday = _yesterday_iso()
    md = _read_report(f"{yesterday}-daily")
    if md is None:
        md, _ = _gen_daily(target_date=yesterday)
    return {"date": yesterday, "markdown": md}
