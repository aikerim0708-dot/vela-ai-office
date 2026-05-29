"""
Telegram Mini App auth — HMAC проверка initData.

Когда Mini App открывается в Telegram, Telegram кладёт в URL `initData` —
строку с подписью на основе bot token. Backend проверяет подпись и достаёт
user_id, чтобы убедиться что запрос действительно от Telegram, а не
подделан.

Документация: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Использование в FastAPI:

    from telegram_auth import verify_telegram_init_data, get_user_id

    @app.post("/api/tasks")
    async def create_task(
        request: Request,
        init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    ):
        if not verify_telegram_init_data(init_data):
            raise HTTPException(401, "Invalid Telegram signature")
        user_id = get_user_id(init_data)
        if user_id not in ALLOWED_USER_IDS:
            raise HTTPException(403, "User not whitelisted")
        ...
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Optional, Tuple
from urllib.parse import parse_qsl

# TTL — auth_date не старше N секунд (защита от replay-атак)
INIT_DATA_TTL_SECONDS = 24 * 3600  # 24 часа

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _secret_key(bot_token: str) -> bytes:
    """Генерирует ключ для HMAC проверки.

    По спеке Telegram:
        secret_key = HMAC_SHA256("WebAppData", bot_token)
    """
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def verify_telegram_init_data(
    init_data: str,
    bot_token: Optional[str] = None,
    ttl_seconds: int = INIT_DATA_TTL_SECONDS,
) -> bool:
    """Проверяет подпись initData от Telegram Mini App.

    Args:
        init_data: строка вида "query_id=...&user=...&auth_date=...&hash=..."
        bot_token: токен бота (по умолчанию из env)
        ttl_seconds: максимальный возраст auth_date

    Returns:
        True если подпись валидна и не истёк TTL.
    """
    token = bot_token or BOT_TOKEN
    if not token:
        return False
    if not init_data:
        return False

    try:
        # Парсим query string в dict
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return False

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return False

    # Проверка TTL: auth_date — unix timestamp
    auth_date_str = parsed.get("auth_date", "")
    if not auth_date_str.isdigit():
        return False
    auth_date = int(auth_date_str)
    if time.time() - auth_date > ttl_seconds:
        return False

    # Строим data-check-string: ключи отсортированы, склеены через \n
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    secret = _secret_key(token)
    expected_hash = hmac.new(
        secret, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # constant-time сравнение
    return hmac.compare_digest(expected_hash, received_hash)


def get_user_id(init_data: str) -> Optional[int]:
    """Достаёт user_id из initData.

    Возвращает None если не получилось распарсить.
    Не проверяет подпись! Вызывай ПОСЛЕ verify_telegram_init_data.
    """
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        user_json = parsed.get("user", "")
        if not user_json:
            return None
        user_data = json.loads(user_json)
        uid = user_data.get("id")
        return int(uid) if uid is not None else None
    except Exception:
        return None


def get_user_info(init_data: str) -> Optional[dict]:
    """Достаёт весь user-блок: id, first_name, username, language_code и т.д."""
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        user_json = parsed.get("user", "")
        if not user_json:
            return None
        return json.loads(user_json)
    except Exception:
        return None


def parse_allowed_user_ids() -> set:
    """Читает whitelist из env."""
    raw = os.environ.get("ALLOWED_TELEGRAM_USER_IDS", "").strip()
    return {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
