# VELA AI Office — Telegram Mini App

> Реализация по уроку Модуля 3 курса airoomclub.ru (Aleksei Ulianov / maxtreysi), адаптация для бизнеса VELA на Wildberries.

## Что это

Локальный scaffold AI Office как Telegram Mini App. Пока работает только локально (Stage 0–3). Для запуска как настоящего Telegram Mini App нужен VDS + домен + SSL — инструкция в `DEPLOY.md`.

## Архитектура (из конспекта урока)

```
Telegram Mini App (фронт, HTML+JS на старте — потом можно переделать на React/Vite)
        │
        ▼
FastAPI Backend (Python)
        │
        ├── AgentProvider interface
        │       ├── MockAgentProvider     ← сейчас активен (заглушки)
        │       └── ClaudeAgentProvider   ← Stage 5, подключение реальных скиллов VELA
        │
        ├── SQLite DB (история задач)
        │
        └── Telegram auth (initData HMAC) ← Stage 2 после деплоя
```

## Команда агентов VELA (Фаза 1, пилот)

| Slug | Имя | Что делает | Связь со скиллом |
|---|---|---|---|
| `daily-report` | Аналитик дня | Утренний отчёт VELA, оцифровка дня | `vela-daily-report` |
| `bid-manager` | Менеджер ставок | Черновики корректировок ставок | `vela-bid-manager` |
| `cluster-health` | Здоровье кластеров | Мониторинг CTR/CR/EPC, алерты | `vela-cluster-health` |
| `unit-econ` | Юнит-экономист | Sanity-check решений по цене/закупу | `vela-unit-econ` |
| `supervisor` | Координатор | Связывает агентов, эскалация | `vela-supervisor` |

## Структура папок

```
vela-ai-office/
  backend/
    app.py            # FastAPI приложение
    agents.py         # AgentProvider, MockAgentProvider
    models.py         # User, Agent, TaskRun, Conversation, Message
    db.py             # SQLite инициализация
    requirements.txt  # FastAPI, uvicorn, pydantic
  frontend/
    index.html        # Главная: список агентов, дашборд
    agent.html        # Страница агента: шаблоны, форма задачи
    style.css         # Стиль как у maxtreysi
    app.js            # Вызовы API
  data/
    office.db         # SQLite (создаётся автоматически)
  DEPLOY.md           # Инструкция выкатки на VDS
  README.md           # этот файл
```

## Как запустить локально

```bash
cd vela-ai-office/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Открыть в браузере: `http://localhost:8000/`

## Стадии разработки (7 шагов автора курса)

- [x] **Stage 0:** Структура папок
- [ ] **Stage 1:** FastAPI + MockAgentProvider + 3 агента
- [ ] **Stage 2:** HTML интерфейс
- [ ] **Stage 3:** Локальный запуск + проверка
- [ ] **Stage 4:** Telegram auth + allowlist (после VDS)
- [ ] **Stage 5:** Подключение реальных скиллов VELA (ClaudeAgentProvider)
- [ ] **Stage 6:** Деплой на VDS (nginx + systemd + HTTPS + BotFather)
- [ ] **Stage 7:** Hardening (rate limits, log redaction, smoke tests)

## ROI-realtalk

Mini App = красивая обёртка. Реальную прибыль VELA двигают **сами агенты**, не интерфейс. До Stage 6 (деплой) Mini App работает только на твоём компьютере и не заменяет Telegram-бота.

**Альтернатива без Mini App** (то что мы уже почти собрали): Telegram-группа VELA Office (✅ создана) + бот @vela_office_bot (✅ админ) + cron + Hermes/Claude. Работает 1-2 часа от подключения данных, не требует VDS.

**Mini App имеет смысл если:** (1) хочешь дать доступ команде, (2) важен бренд/презентация инвесторам, (3) готова платить за VDS $5-20/мес.
