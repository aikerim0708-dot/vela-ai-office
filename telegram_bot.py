"""
Telegram-бот VELA Office — вариант B (один бот, имитация команды).

Один бот @vela_wb_bot, но имитирует команду из 5 агентов через @-упоминания.
Пользователь пишет «@Лео что с кампанией» → бот вызывает конкретно Лео и
отвечает от его имени: «🦁 Лео: ...». Если @-упоминания нет — Макс
делегирует команде через orchestrate_goal.

Запуск:
    .venv/bin/python telegram_bot.py

Зависимости:
    python-telegram-bot==21.0
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import httpx

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        CallbackQueryHandler,
        filters,
    )
except ImportError:
    print("pip install python-telegram-bot==21.0", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


# ────────── Конфигурация ──────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
VELA_API_URL = os.environ.get("VELA_API_URL", "http://127.0.0.1:8000").rstrip("/")

_raw_allowed = os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").strip()
ALLOWED_USER_IDS: List[int] = [
    int(x.strip()) for x in _raw_allowed.split(",") if x.strip().isdigit()
]

TELEGRAM_MAX_MESSAGE = 4000

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("vela-bot")


# ────────── Команда агентов ──────────
AGENTS = {
    "max":  {"emoji": "👨‍💼", "name": "Макс", "role": "Chief / координатор"},
    "leo":  {"emoji": "🦁",  "name": "Лео",  "role": "Performance Marketing"},
    "anna": {"emoji": "📦",  "name": "Анна", "role": "Supply / поставки"},
    "zara": {"emoji": "💰",  "name": "Зара", "role": "CFO / финансы"},
    "eva":  {"emoji": "🎨",  "name": "Ева",  "role": "Marketing / контент"},
}

# Маппинг имён в @-упоминаниях → slug агента
MENTION_MAP = {
    "лео": "leo", "leo": "leo", "left": "leo",
    "анна": "anna", "anna": "anna", "ann": "anna", "ann_a": "anna",
    "зара": "zara", "zara": "zara",
    "ева": "eva", "eva": "eva", "ева_": "eva",
    "макс": "max", "max": "max", "макс_": "max",
}

MENTION_RE = re.compile(r"@([\wа-яА-ЯёЁ_-]+)", re.IGNORECASE)


# ────────── Проверки ──────────
def _check_config() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN":
        log.error("TELEGRAM_BOT_TOKEN не задан в .env")
        sys.exit(1)
    if not ALLOWED_USER_IDS:
        log.error("ALLOWED_TELEGRAM_USER_IDS не задан. Узнать свой ID: @userinfobot")
        sys.exit(1)
    log.info(
        "Бот готов. Whitelist: %s user(s). API: %s. Команда: %s",
        len(ALLOWED_USER_IDS),
        VELA_API_URL,
        list(AGENTS.keys()),
    )


def _is_allowed(uid: Optional[int]) -> bool:
    return uid is not None and uid in ALLOWED_USER_IDS


async def _reject(update: Update) -> None:
    user = update.effective_user
    log.warning("Отклонён: uid=%s @%s", user.id if user else "?", user.username if user else "?")
    if update.message:
        await update.message.reply_text("Доступ к VELA не предоставлен.")


# ────────── Парсинг сообщения ──────────
def detect_mentioned_agent(text: str) -> Optional[str]:
    """Ищет @упоминание агента в тексте. Возвращает slug или None."""
    for m in MENTION_RE.finditer(text):
        name = m.group(1).lower().rstrip("_")
        if name in MENTION_MAP:
            return MENTION_MAP[name]
    # Без @ — пробуем «Лео,», «Анна:», «Зара —»
    first_word = re.split(r"[,:\-\s]", text.strip(), maxsplit=1)[0].lower().rstrip("_")
    if first_word in MENTION_MAP:
        return MENTION_MAP[first_word]
    return None


def strip_mention(text: str, agent_slug: str) -> str:
    """Убирает @упоминание агента из текста."""
    out = MENTION_RE.sub("", text).strip()
    # Убираем варианты «Лео, » в начале
    out = re.sub(r"^[А-Яа-яA-Za-z]+[,:\-\s]+", "", out, count=1).strip()
    return out or text


def format_agent_reply(agent_slug: str, content: str) -> str:
    """Форматирует ответ от имени агента: 🦁 **Лео:** ..."""
    a = AGENTS.get(agent_slug, AGENTS["max"])
    header = f"{a['emoji']} *{a['name']}* ({a['role']}):"
    return f"{header}\n\n{content}"


# ────────── Команды ──────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not _is_allowed(user.id):
        await _reject(update)
        return

    text = (
        f"Привет, {user.first_name}.\n\n"
        "Это VELA AI Office. Команда из 5 агентов:\n\n"
        "👨‍💼 Макс — Chief / координатор\n"
        "🦁 Лео — реклама и ставки\n"
        "📦 Анна — остатки и поставки\n"
        "💰 Зара — финансы и маржа\n"
        "🎨 Ева — карточки и отзывы\n\n"
        "Как писать:\n"
        "• `@Лео что с ДРР бритвы` — прямой вопрос Лео\n"
        "• `что с продажами` — Макс сам делегирует\n"
        "• `Зара, маржа за май?` — Зара ответит\n\n"
        "Команды:\n"
        "/agents — список команды\n"
        "/digest — утренний дайджест\n"
        "/health — проверка WB API\n"
        "/report — последний Vela Daily"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await _reject(update)
        return
    lines = ["*Команда VELA AI Office:*\n"]
    for slug, a in AGENTS.items():
        lines.append(f"{a['emoji']} *{a['name']}* — {a['role']}")
        lines.append(f"   _Упоминай: @{slug} или @{a['name']}_\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await _reject(update)
        return
    await update.message.reply_text("Готовлю утренний дайджест…")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(f"{VELA_API_URL}/api/digest/morning")
        if r.status_code != 200:
            await update.message.reply_text(f"VELA API {r.status_code}")
            return
        data = r.json()
        text = data.get("digest") or str(data)[:TELEGRAM_MAX_MESSAGE]
        await _send_long(update, format_agent_reply("max", text))
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await _reject(update)
        return
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{VELA_API_URL}/api/reports/latest/daily")
        if r.status_code != 200:
            await update.message.reply_text(f"VELA API {r.status_code}")
            return
        data = r.json()
        md = data.get("markdown", "")
        await _send_long(update, f"📅 *Vela Daily за {data.get('date', '?')}*\n\n{md[:3500]}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await _reject(update)
        return
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{VELA_API_URL}/api/wb/health")
        data = r.json()
        tokens = data.get("tokens", {})
        ok = data.get("ok", False)
        lines = ["*WB API health:*"]
        for name, info in tokens.items():
            mark = "✅" if info.get("ok") else "❌"
            status = info.get("status", "?")
            rate = " (rate limit)" if info.get("rate_limited") else ""
            lines.append(f"{mark} {name}: HTTP {status}{rate}")
        lines.append(f"\nИТОГО: {'✅ ok' if ok else '⚠️ требует внимания'}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Ошибка health: {e}")


# Быстрые команды для агентов
def _make_quick_agent_command(slug: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _is_allowed(update.effective_user.id):
            await _reject(update)
            return
        prompt = " ".join(context.args) if context.args else "Что у тебя нового?"
        await _call_agent(update, slug, prompt)
    return handler


# ────────── Обычное сообщение ──────────
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await _reject(update)
        return

    user_text = (update.message.text or "").strip()
    if not user_text:
        return

    log.info("uid=%s msg=%r", update.effective_user.id, user_text[:80])
    await update.message.chat.send_action("typing")

    mentioned = detect_mentioned_agent(user_text)
    if mentioned and mentioned != "max":
        prompt = strip_mention(user_text, mentioned)
        await _call_agent(update, mentioned, prompt)
    else:
        # Без @-упоминания или @Макс → orchestrate (Макс делегирует)
        await _call_orchestrate(update, user_text)


async def _call_agent(update: Update, slug: str, prompt: str) -> None:
    """Прямой вызов одного агента через /api/tasks."""
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                f"{VELA_API_URL}/api/tasks",
                json={"agent_slug": slug, "prompt": prompt},
            )
        if r.status_code != 200:
            await update.message.reply_text(f"VELA API {r.status_code}: {r.text[:200]}")
            return
        data = r.json()
        answer = data.get("output") or str(data)
        await _send_long(update, format_agent_reply(slug, answer))
    except httpx.ConnectError:
        await update.message.reply_text("VELA API недоступен. Запусти vela.service на VDS.")
    except Exception as e:
        log.exception("_call_agent error")
        await update.message.reply_text(f"Ошибка: {e}")


async def _call_orchestrate(update: Update, goal: str) -> None:
    """Макс делегирует команде через /api/orchestrate."""
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                f"{VELA_API_URL}/api/orchestrate",
                json={"goal": goal, "include_wb_data": True},
            )
        if r.status_code != 200:
            await update.message.reply_text(f"VELA API {r.status_code}")
            return
        data = r.json()

        # Сначала шлём ответ каждого агента отдельным сообщением (имитация группового чата)
        for ar in data.get("agent_results", []) or []:
            agent = ar.get("agent", "max")
            out = ar.get("output", "")
            if out:
                await _send_long(update, format_agent_reply(agent, out[:2500]))

        # Потом итог от Макса
        final = data.get("final_summary") or data.get("answer") or "—"
        await _send_long(update, format_agent_reply("max", f"*Свод:*\n\n{final}"))
    except httpx.ConnectError:
        await update.message.reply_text("VELA API недоступен.")
    except Exception as e:
        log.exception("orchestrate error")
        await update.message.reply_text(f"Ошибка: {e}")


async def _send_long(update: Update, text: str) -> None:
    if len(text) <= TELEGRAM_MAX_MESSAGE:
        try:
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception:
            # Если Markdown не парсится — без форматирования
            await update.message.reply_text(text)
        return
    for i in range(0, len(text), TELEGRAM_MAX_MESSAGE):
        try:
            await update.message.reply_text(text[i:i + TELEGRAM_MAX_MESSAGE], parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(text[i:i + TELEGRAM_MAX_MESSAGE])


# ────────── Точка входа ──────────
def main() -> None:
    _check_config()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("agents", cmd_agents))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("health", cmd_health))
    # Быстрые команды для каждого агента: /leo, /anna, /zara, /eva, /max
    for slug in AGENTS.keys():
        app.add_handler(CommandHandler(slug, _make_quick_agent_command(slug)))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Polling…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
