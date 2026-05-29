# Поднять Telegram-бота VELA — 15 минут

После этого можно писать боту с телефона, получать дайджест и общаться с агентами.

---

## Шаг 1. Создать бота через @BotFather (3 мин)

1. Открой @BotFather в Telegram
2. Команда `/newbot`
3. Имя бота (как видит пользователь): `VELA Office` (или любое)
4. Username бота: `vela_office_bot` (или любой, должен заканчиваться на `_bot`)
5. BotFather пришлёт **токен** вида:
   ```
   8123456789:AAHHHabcDEFghijkl-mnopQRST
   ```
6. **Скопируй токен и пришли мне** — я положу в `.env`

## Шаг 2. Узнать свой Telegram user_id (1 мин)

1. Открой @userinfobot в Telegram
2. Напиши ему `/start`
3. Получишь свой `user_id` (формат: 9-10 цифр)
4. **Пришли мне этот id** — я положу в `ALLOWED_TELEGRAM_USER_IDS`

Это whitelist — без этого никто не сможет писать боту (включая тебя).

## Шаг 3. Иконка и описание бота (опционально, 2 мин)

В @BotFather:
- `/setdescription` — что бот делает
- `/setabouttext` — короткое описание
- `/setuserpic` — аватарка (лого VELA если есть)

## Шаг 4. Mini App URL (когда VDS поднят, 2 мин)

В @BotFather:
- `/mybots` → твой бот → **Bot Settings** → **Menu Button**
- Выбрать **Configure Menu Button**
- Текст кнопки: `Открыть VELA`
- URL: `https://<твой_домен>/` (или `https://vela-prod.tw1.ru/` если используешь поддомен Timeweb)

После этого в любом чате с ботом появится кнопка снизу — клик откроет твой Mini App.

## Шаг 5. Запуск бота

### Локально (на твоём mac, для теста)

```bash
cd "$HOME/Documents/Claude/Projects/ИИ офис/vela-ai-office/backend"
source .venv/bin/activate
pip install python-telegram-bot==21.0
python telegram_bot.py
```

Бот заработает в polling-режиме пока окно открыто. Попиши ему — Макс ответит.

### На VDS (постоянно)

В `setup_vds.sh` уже подготовлен service. После заполнения `.env`:

```bash
ssh vela@<IP>
sudo systemctl enable vela-bot
sudo systemctl start vela-bot
sudo journalctl -u vela-bot -f
```

---

## Безопасность

Бот защищён двумя слоями:

1. **Whitelist по user_id** (в `telegram_bot.py`)
   - В `.env`: `ALLOWED_TELEGRAM_USER_IDS=123456789,987654321`
   - Любой кто не в списке получает «Доступ не предоставлен», даже если знает username бота.

2. **HMAC-проверка initData** для Mini App (в `telegram_auth.py`)
   - Когда Mini App открывается → Telegram кладёт подпись в URL
   - Backend проверяет подпись через `bot_token` — никто не может подделать запрос
   - Дополнительная проверка whitelist на уровне backend

3. **TTL 24 часа** на initData — старые URL не работают (защита от replay).

---

## Что мне прислать чтобы я подключил бот

1. **Токен от BotFather** (формат `XXXXXXXX:AAH...`)
2. **Твой Telegram user_id** (от @userinfobot, 9-10 цифр)
3. **URL Mini App** (если уже поднят VDS — IP или домен)

После этого я обновлю `.env` и можно тестировать.

---

## Чек-лист

- [ ] Бот создан через @BotFather
- [ ] Токен бота передан Claude
- [ ] user_id получен и передан Claude
- [ ] Бот запущен локально (для теста)
- [ ] Бот отвечает на `/start`
- [ ] Бот отвечает на свободный текст через Макса
- [ ] (когда VDS) бот развёрнут на VDS как systemd service
- [ ] (когда VDS) Mini App URL настроен в BotFather
