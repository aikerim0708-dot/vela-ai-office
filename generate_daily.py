#!/usr/bin/env python3
"""
Запускается cron'ом на VDS каждое утро в 7:00.
Генерирует Vela Daily за прошедший день и отправляет TL;DR в Telegram.

Запуск:
    cd /home/vela/vela-ai-office/backend
    .venv/bin/python scripts/generate_daily.py

Cron:
    0 7 * * * /home/vela/vela-ai-office/backend/.venv/bin/python /home/vela/vela-ai-office/backend/scripts/generate_daily.py >> /home/vela/logs/daily.log 2>&1
"""
import logging
import os
import sys
from pathlib import Path

# Корень backend в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

# Загрузка .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("generate_daily")


def main():
    from reports import generate_daily, yesterday_iso

    target = yesterday_iso()
    log.info("Старт генерации daily за %s", target)

    md, meta = generate_daily(target_date=target)
    log.info("Готов отчёт: %d символов", len(md))

    # Отправка TL;DR в Telegram
    try:
        send_to_telegram(meta, md)
    except Exception as e:
        log.exception("Не удалось отправить в Telegram: %s", e)


def send_to_telegram(meta: dict, md: str) -> None:
    """Отправляет первые 4000 символов отчёта в чат Айкерим."""
    import httpx

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    user_ids_raw = os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").strip()
    if not bot_token or not user_ids_raw:
        log.warning("TELEGRAM_BOT_TOKEN или ALLOWED_TELEGRAM_USER_IDS не заданы — пропускаем отправку")
        return

    user_ids = [int(x.strip()) for x in user_ids_raw.split(",") if x.strip().isdigit()]
    if not user_ids:
        return

    # TL;DR = первые 2000 символов отчёта (Telegram лимит 4096)
    target = meta.get("date", "")
    api_url = os.environ.get("VELA_API_URL", "https://vela.example.com").rstrip("/")
    tl_dr = md[:2000]
    if len(md) > 2000:
        tl_dr += f"\n\n…\n\n[Полный отчёт]({api_url}/reports/{target})"

    for uid in user_ids:
        log.info("Отправляю TL;DR пользователю %s", uid)
        try:
            r = httpx.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": uid,
                    "text": tl_dr,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=30.0,
            )
            if r.status_code != 200:
                log.warning("Telegram %s вернул %s: %s", uid, r.status_code, r.text[:200])
        except Exception as e:
            log.exception("ошибка отправки %s: %s", uid, e)


if __name__ == "__main__":
    main()
