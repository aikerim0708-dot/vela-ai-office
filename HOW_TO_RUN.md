# Как запустить VELA AI Office локально

## Быстрый старт (5 минут)

1. Открой Терминал на Mac (Cmd+Space → «Терминал»)

2. Перейди в папку проекта:
   ```bash
   cd ~/Documents/Claude/Projects/ИИ\ офис/vela-ai-office/backend
   ```

3. Создай виртуальное окружение Python (один раз):
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Запусти сервер:
   ```bash
   uvicorn app:app --reload --port 8000
   ```

5. Открой в браузере: **http://localhost:8000**

## Что увидишь

- Главная: дашборд как у maxtreysi — 5 агентов команды, статус «✨ Всё под контролем», метрики сервера, быстрый доступ к задачам и активности.
- Клик на агента → страница с шаблонами задач и формой запуска.
- Сейчас всё работает на MOCK-данных (заглушках) — реальные скиллы VELA подключим в Stage 5.

## Что работает сейчас

✅ 5 агентов VELA (Аналитик дня, Менеджер ставок, Здоровье кластеров, Юнит-экономист, Координатор)
✅ Шаблоны задач для каждого агента
✅ История задач сохраняется в SQLite
✅ API endpoints (GET /api/health, /api/agents, POST /api/tasks)
✅ Mobile-friendly интерфейс (адаптирован под Telegram Mini App, ширина до 480px)

## Что НЕ работает (по плану — следующие стадии)

❌ Реальные ответы агентов (сейчас MOCK) → Stage 5
❌ Telegram-авторизация → Stage 4
❌ Доступ извне (только localhost) → Stage 6
❌ Подключение к WB Seller API → потом

## Остановить сервер

В терминале нажми `Ctrl+C`.

## API напрямую (если нужно тестировать)

```bash
# Список агентов
curl http://localhost:8000/api/agents

# Запустить задачу
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"agent_slug": "daily-report", "prompt": "Утренний отчёт"}'

# История
curl http://localhost:8000/api/tasks
```
