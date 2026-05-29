# CLAUDE.md — память проекта VELA Office

Файл читается Claude Code/Cowork при каждом старте сессии в этом проекте.
Если меняешь архитектуру — обновляй этот файл, а не догадывайся.

---

## Что это

**VELA AI Office** — Telegram Mini App, в котором 5 ИИ-агентов помогают управлять бизнесом VELA на Wildberries. Цель — рост **чистой прибыли** (не активности).

Два товара VELA:
- **Бритва** — рекламная кампания WB id **29230612**
- **Накладные ресницы** — рекламная кампания WB id **32284868**

---

## Стек

- **Backend:** Python **3.9** + FastAPI + uvicorn (`--reload`)
- **Frontend:** vanilla HTML/CSS/JS (`frontend/index.html`, `frontend/app.js`)
- **DB:** SQLModel (SQLite файл в `data/`)
- **LLM:** Claude Sonnet 4-5 через Anthropic API (ключ в `.env`)
- **WB API:** 3 токена с маршрутизацией по hostname (см. `docs/wb_tokens_matrix.md`)
- **Запуск:** `VELA_запуск.command` в корне (двойной клик)
- **Обновление токенов:** `VELA_обновить_токен.command`

**ВАЖНО про Python 3.9:**
- НЕ использовать `str | None` — только `Optional[str]` из `typing`
- НЕ использовать `dict[str, int]` без `from __future__ import annotations`
- При сомнении — добавь `from __future__ import annotations` в начало файла

---

## Структура

```
vela-ai-office/
├── backend/
│   ├── app.py              # FastAPI приложение, endpoints, dotenv
│   ├── agents.py           # 5 агентов + ClaudeAgentProvider + orchestrate_goal
│   ├── brain.py            # Brain VELA: гипотезы, кластеры, события
│   ├── inbox.py            # Knowledge Inbox
│   ├── wb_client.py        # WB API клиент с маршрутизацией host → токен
│   ├── wb_api.py           # старый WB класс (legacy)
│   ├── wb_tools.py         # tools для агентов
│   ├── db.py               # SQLModel модели + init_db
│   ├── .env                # секреты — НЕ коммитить в git
│   └── .venv/              # virtualenv
├── frontend/
│   ├── index.html          # главная Mini App
│   └── app.js              # KPI, Inbox, чат
├── docs/
│   ├── wb_tokens_matrix.md # архитектура 3 токенов (раз и навсегда)
│   └── course_notes.md     # конспект курса AI Room
├── data/                   # БД, кэши — НЕ коммитить
├── skills/                 # SKILL.md файлы для агентов (Анна/Ева)
├── VELA_запуск.command     # двойной клик → uvicorn
└── VELA_обновить_токен.command  # двойной клик → обновить токены WB
```

---

## 5 агентов

В `backend/agents.py` — каждый агент имеет роль и системный промпт.

| Агент | Роль | WB-домены |
|---|---|---|
| **Макс** (CEO) | координатор, делегирует через `orchestrate_goal()` | ничего напрямую |
| **Лео** (Performance) | реклама, ставки, кластеры | advert-api |
| **Анна** (Supply) | остатки, заказы, поставки | statistics-api, supplies-api, marketplace-api |
| **Зара** (CFO) | продажи, маржа, цены | statistics-api, finance-api, discounts-prices-api |
| **Ева** (Marketing) | карточки, отзывы, ТЗ дизайнеру | content-api, feedbacks-api |

Делегирование: Макс получает задачу → `orchestrate_goal()` → передаёт нужным агентам параллельно → сводит итог.

---

## WB-токены (важно!)

3 токена с маршрутизацией по hostname (см. `docs/wb_tokens_matrix.md`):

| Переменная | Scope | Права |
|---|---|---|
| `WB_TOKEN_READ` | Аналитика + Статистика + Финансы | только чтение |
| `WB_TOKEN_ADS` | Продвижение | чтение + запись |
| `WB_TOKEN_MANAGE` | Контент + Маркетплейс + Отзывы + Цены + Поставки | чтение + запись |

**Никогда не маршрутизировать токен по агенту** — только по hostname API. Один host = один scope = один токен.

**Важные особенности WB API (по состоянию на 2026-05-28):**
- `/adv/v2/fullstats` УДАЛЁН (404). Использовать только `/adv/v3/fullstats`
- `/adv/v3/fullstats` принимает **только GET** (POST → 405). Параметр `ids` повторяется: `?ids=A&ids=B&dateFrom=...&dateTo=...`
- Rate limits: `/adv/v1/promotion/count` ~1/5сек, `/api/v1/supplier/sales` ~1/мин, `/api/v1/feedbacks/count` ~1/мин

---

## Принципы работы Айкерим

- **НЕ работает с терминалом** → любая команда должна быть в `.command` файле или через UI
- **Python 3.9** локально → не использовать 3.10+ синтаксис
- **Cmd+V в Terminal иногда не срабатывает** → инструкции через .command или Finder
- **Главный KPI — чистая прибыль VELA**, не «красивый офис» и не количество фич
- **Хочет конкретику**: цифры, сроки, ROI. Не теорию.

---

## Что делать НЕЛЬЗЯ

1. **Коммитить в git** файлы из этого списка (всегда проверять `.gitignore`):
   - `backend/.env`
   - `backend/.env.backup_*`
   - `data/*`
   - `backend/.venv/*`
   - любые JWT-токены
   - `ANTHROPIC_API_KEY`

2. **Парсить scope из JWT-payload** (поле `s`) — наш парсер сбойнул 28.05.2026, проверка через API curl надёжнее.

3. **Менять схему токенов** без обновления `docs/wb_tokens_matrix.md` и `CLAUDE.md`.

4. **Удалять .command-файлы** — это единственный путь Айкерим запустить/обновить систему.

5. **Использовать Claude Code как 24/7 бота через подписку** — это серая зона Anthropic ToS. Только Claude API через ключ.

6. **Делать `str | None` в type hints** — Python 3.9 не поддерживает в runtime, только `Optional[str]`.

---

## Что делать НУЖНО

- При любой ошибке WB API >= 400 — смотреть на сам ответ (`requestId`, `title`, `detail`), а не гадать.
- Для долгих изменений — делать `.env.backup_*` перед `Write`.
- Перед утверждением «scope X недоступен» — проверить через `curl` к реальному endpoint. 429 ≠ битый токен.
- При создании файла-инструмента для Айкерим — обязательно `chmod +x` (иначе двойной клик не сработает).

---

## Контекст текущей задачи (обновлять при смене фокуса)

**Что готово (28.05.2026):**
- Mini App с KPI и Inbox
- 5 агентов + delegation через `orchestrate_goal`
- 3 WB-токена живые (READ/ADS/MANAGE), все scope подтверждены
- Утренний дайджест `/api/digest/morning`
- Knowledge Inbox с автоклассификацией
- Реактивные цепочки в Brain

**Что в очереди:**
- Скилл Евы — карточки и тексты (PAS-фреймворк из Corey Haines marketing skills)
- Скилл Анны — план остатков и поставок
- Структурированный brief вместо свободного текста для всех агентов
- Шаблоны промптов на главной Mini App
- Telegram-бот (+ HMAC initData + whitelist user IDs)
- VDS (+ deploy key + verify-no-secrets + nginx HTTPS + systemd)

См. полный TODO в `docs/course_notes.md`.

---

## Куда обращаться при сомнениях

| Вопрос | Где смотреть |
|---|---|
| «Какой токен для какого host?» | `docs/wb_tokens_matrix.md` |
| «Что было сделано за сессию X?» | `git log` |
| «Какие принципы курса применили?» | `docs/course_notes.md` |
| «Как агенты общаются?» | `backend/agents.py` → `orchestrate_goal()` |
| «Какие WB API endpoints используем?» | `backend/wb_client.py` → классы `WBClient` |
