# Деплой VELA AI Office на VDS (Stage 6)

> Эта инструкция — для разработчика, который будет деплоить.
> Айкерим: отдай этот файл разработчику + дай доступ к VDS и доменy.

## Что нужно от Айкерим перед деплоем

| Требуется | Где взять | Цена |
|---|---|---|
| **VDS** (1 vCPU, 1GB RAM, Ubuntu 22.04) | Timeweb, Selectel, DigitalOcean | $5–10/мес |
| **Домен** (например `office.vela.ru`) | reg.ru, GoDaddy | 200–800 ₽/год |
| **Бот Telegram** | @BotFather (уже есть `@vela_office_bot`) | 0 ₽ |
| **API ключ Claude** (для Stage 5) | console.anthropic.com | по usage, ~$5–20/мес |

## Архитектура продакшен

```
Пользователь Telegram
  → BotFather menu button → открывает office.vela.ru в Mini App
  → nginx (HTTPS, Let's Encrypt)
  → uvicorn (FastAPI) на 127.0.0.1:8000
  → SQLite в /var/lib/vela-office/office.db
  → Claude API (для реальных агентов)
```

## Стадия 1: подготовка VDS

```bash
# На VDS под root
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv nginx certbot python3-certbot-nginx git ufw

# Создать пользователя для приложения (не запускать от root!)
useradd -m -s /bin/bash velaoffice
mkdir -p /var/lib/vela-office
chown velaoffice:velaoffice /var/lib/vela-office

# Firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

## Стадия 2: загрузить код

```bash
# Под velaoffice
su - velaoffice
git clone <repo_url> /home/velaoffice/vela-ai-office
cd /home/velaoffice/vela-ai-office/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Стадия 3: systemd-сервис

`/etc/systemd/system/vela-office.service`:

```ini
[Unit]
Description=VELA AI Office API
After=network.target

[Service]
Type=simple
User=velaoffice
WorkingDirectory=/home/velaoffice/vela-ai-office/backend
Environment="VELA_DB_PATH=/var/lib/vela-office/office.db"
Environment="VELA_TG_BOT_TOKEN=<токен_бота>"
Environment="VELA_TG_ALLOWED_IDS=123456789"
Environment="ANTHROPIC_API_KEY=sk-ant-..."
ExecStart=/home/velaoffice/vela-ai-office/backend/.venv/bin/uvicorn app:app \
  --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable vela-office
systemctl start vela-office
systemctl status vela-office
```

## Стадия 4: nginx + HTTPS

`/etc/nginx/sites-available/vela-office`:

```nginx
server {
  listen 80;
  server_name office.vela.ru;
  return 301 https://$server_name$request_uri;
}

server {
  listen 443 ssl http2;
  server_name office.vela.ru;

  ssl_certificate /etc/letsencrypt/live/office.vela.ru/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/office.vela.ru/privkey.pem;

  # Mini App требует strict CSP — настроим в Stage 7

  location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

```bash
ln -s /etc/nginx/sites-available/vela-office /etc/nginx/sites-enabled/
certbot --nginx -d office.vela.ru
nginx -t && systemctl reload nginx
```

## Стадия 5: BotFather Mini App menu button

В Telegram → @BotFather:

```
/mybots → @vela_office_bot → Bot Settings → Menu Button
URL: https://office.vela.ru
Text: AI Office
```

## Стадия 6: Telegram-авторизация в коде (Stage 4 курса)

В `backend/app.py` добавить middleware который проверяет `Telegram.WebApp.initData` через HMAC.

Псевдокод (полная реализация ~50 строк):

```python
from fastapi import Header, HTTPException
import hmac, hashlib, json
from urllib.parse import parse_qsl

def verify_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400):
    parsed = dict(parse_qsl(init_data))
    if "hash" not in parsed:
        raise HTTPException(401, "no hash")
    received_hash = parsed.pop("hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if expected_hash != received_hash:
        raise HTTPException(401, "bad hash")
    # Проверить auth_date
    auth_date = int(parsed.get("auth_date", 0))
    import time
    if time.time() - auth_date > max_age_seconds:
        raise HTTPException(401, "expired")
    user = json.loads(parsed.get("user", "{}"))
    return user

# Allowlist
ALLOWED_TG_IDS = [int(x) for x in os.environ.get("VELA_TG_ALLOWED_IDS", "").split(",") if x]

@app.middleware("http")
async def telegram_auth_middleware(request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        init_data = request.headers.get("x-telegram-init-data")
        if not init_data:
            return JSONResponse({"detail": "no auth"}, status_code=401)
        user = verify_telegram_init_data(init_data, os.environ["VELA_TG_BOT_TOKEN"])
        if user.get("id") not in ALLOWED_TG_IDS:
            return JSONResponse({"detail": "not allowed"}, status_code=403)
        request.state.user = user
    return await call_next(request)
```

Во фронте (`app.js`) при каждом fetch добавлять заголовок:

```javascript
const initData = window.Telegram?.WebApp?.initData || "";
fetch(url, { headers: { "X-Telegram-Init-Data": initData } });
```

## Стадия 7: Подключение реальных агентов (Stage 5 курса)

Заменить `MockAgentProvider` на `ClaudeAgentProvider`. Псевдокод:

```python
# backend/agents.py
from anthropic import Anthropic
import os

class ClaudeAgentProvider:
    def __init__(self):
        self.client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        # Загрузить скиллы VELA из hermes_skills/
        # Маппинг slug → системный промпт скилла
        self.skills = {
            "daily-report": load_skill("hermes_skills/vela-daily-report/SKILL.md"),
            "bid-manager": load_skill("hermes_skills/vela-bid-manager/SKILL.md"),
            # ...
        }

    def run_task(self, agent_slug, prompt):
        skill_prompt = self.skills.get(agent_slug)
        msg = self.client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=skill_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "status": "succeeded",
            "output": msg.content[0].text,
            "is_mock": False,
        }
```

В `app.py`:

```python
provider_kind = os.environ.get("VELA_PROVIDER", "mock")
agent_provider = ClaudeAgentProvider() if provider_kind == "claude" else MockAgentProvider()
```

## Стадия 8: Hardening (Stage 7 курса)

- Rate limits через `slowapi`
- Log redaction (не логировать содержимое промптов с PII)
- Smoke tests при каждом деплое
- Бэкап SQLite раз в день (`/var/lib/vela-office/office.db` → S3/B2)
- Health-check мониторинг (UptimeRobot, бесплатно)

## Чек-лист безопасности

- [ ] Бот-токен только в systemd env, никогда в git
- [ ] `ANTHROPIC_API_KEY` только в systemd env
- [ ] HTTPS обязателен (Telegram требует)
- [ ] allowlist Telegram user IDs (нет публичного доступа)
- [ ] `velaoffice` user не root
- [ ] Бэкап БД раз в день
- [ ] `git diff` перед коммитом смотреть на секреты

## Реальная оценка времени для разработчика

| Этап | Часов |
|---|---|
| VDS подготовка + домен + SSL | 1–2 |
| Деплой backend + systemd + nginx | 1 |
| Telegram-авторизация (Stage 4 курса) | 2–3 |
| Подключение реальных агентов через Claude API (Stage 5) | 3–5 |
| Hardening | 2–4 |
| **Итого** | **9–15 часов** |

При ставке 2000 ₽/час: 18 000–30 000 ₽ единоразово + $5–10/мес VDS + ~$20/мес токены Claude.
