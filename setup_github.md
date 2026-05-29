# Создать GitHub-репо для VELA — 10 минут

Делать в браузере. Я не могу сделать это за тебя — нужен твой GitHub-аккаунт.

## Шаг 1. Создать репозиторий (3 мин)

1. Открой https://github.com/new (если не залогинена — войди в GitHub)
2. **Repository name:** `vela-ai-office`
3. **Description:** «VELA AI Office — Mini App с 5 ИИ-агентами для управления WB» (не обязательно)
4. ⚠️ Выбери **Private** — НЕ Public. Здесь будут токены в .env.backup_*, нельзя в открытом доступе.
5. ❌ НЕ ставь галочку «Add a README file» — у нас уже есть
6. ❌ НЕ выбирай .gitignore template — у нас уже свой
7. ❌ НЕ выбирай License
8. Нажми **Create repository**

После создания GitHub покажет страницу с командами «Quick setup» — оттуда возьми SSH-ссылку формата `git@github.com:aikerim0708/vela-ai-office.git`. Пришли её мне.

## Шаг 2. SSH-ключ для твоего mac (если ещё нет, 5 мин)

Проверь — есть ли у тебя SSH-ключ для GitHub. В Terminal:

```bash
ls ~/.ssh/id_ed25519.pub
```

**Если файл существует** — скопируй его содержимое:
```bash
cat ~/.ssh/id_ed25519.pub | pbcopy
```
(теперь ключ в буфере обмена)

**Если файла нет — создай:**
```bash
ssh-keygen -t ed25519 -C "aikerim0708@gmail.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub | pbcopy
```

## Шаг 3. Добавить SSH-ключ в GitHub (2 мин)

1. Открой https://github.com/settings/keys
2. Кликни **New SSH key**
3. **Title:** `Aikerim MacBook`
4. **Key type:** Authentication Key
5. **Key:** вставь из буфера (Cmd+V) — должно начинаться с `ssh-ed25519 AAAAC3...`
6. Нажми **Add SSH key**

## Шаг 4. Проверка соединения

В Terminal:
```bash
ssh -T git@github.com
```
Должно ответить: `Hi aikerim0708! You've successfully authenticated...`

## Готово

Теперь когда у меня есть SSH-ссылка репо — я сделаю первый коммит и push сам (через .command файл).

---

## Что я сделаю когда у тебя будет SSH-link

Создам `VELA_первый_коммит.command` который:
1. Запустит `bash scripts/verify-no-secrets.sh` — проверка что секреты не утекут
2. `git init` + `git remote add origin <твой ssh>`
3. `git add .` + `git commit -m "VELA: initial commit"`
4. `git push -u origin main`

И всё что мы сделали попадёт в твой приватный репо.
