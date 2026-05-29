#!/bin/bash
# Двойной клик — обновляет один из 3 WB-токенов в .env и проверяет что он живой.
# Архитектура: docs/wb_tokens_matrix.md
#   1) WB_TOKEN_READ   — Статистика + Аналитика + Финансы (read-only)
#   2) WB_TOKEN_ADS    — Продвижение (read+write)
#   3) WB_TOKEN_MANAGE — Контент + Отзывы + Цены + Поставки + Маркетплейс (read+write)

cd "$HOME/Documents/Claude/Projects/ИИ офис/vela-ai-office/backend"

clear
echo "════════════════════════════════════════════"
echo "  VELA — обновление WB-токена"
echo "════════════════════════════════════════════"
echo ""
echo "Какой токен обновляем?"
echo ""
echo "  1) READ    — Статистика + Аналитика + Финансы (read-only)"
echo "  2) ADS     — Продвижение (read+write)"
echo "  3) MANAGE  — Контент + Отзывы + Цены и скидки (read+write)"
echo "  4) Все три по очереди"
echo "  0) Выйти"
echo ""
read -p "Введи цифру (0/1/2/3/4): " CHOICE
echo ""

# Функция: обновляет ОДНУ переменную в .env
update_one() {
    local VAR_NAME="$1"   # WB_TOKEN_READ / WB_TOKEN_ADS / WB_TOKEN_MANAGE
    local LABEL="$2"      # человеческое имя для подсказки

    echo "──────────────────────────────────────────"
    echo "Вставляешь токен: $LABEL"
    echo "Скопируй его из заметки в Apple Notes."
    echo "При вставке Cmd+V токен НЕ будет виден (это нормально)."
    echo ""
    read -s -p "Вставь токен и нажми Enter: " TOKEN
    echo ""

    if [ -z "$TOKEN" ]; then
        echo "⏭  Пусто — пропускаю $LABEL"
        return 0
    fi

    # Иногда в заметке вместе с токеном лежит имя ("VELA STAT\neyJ..." или scope-строка)
    # Берём только строку, начинающуюся с eyJ — это и есть JWT
    TOKEN=$(echo "$TOKEN" | grep -oE '^eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$' | head -1)
    if [ -z "$TOKEN" ]; then
        # вторая попытка — поискать в любой строке
        TOKEN=$(echo "$1" | grep -oE 'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' | head -1)
    fi

    if [ -z "$TOKEN" ] || [[ ! "$TOKEN" =~ ^eyJ ]]; then
        echo "❌ Не вижу JWT-формат (eyJ...eyJ...). Пропускаю $LABEL."
        return 1
    fi

    echo "✅ Токен принят (длина ${#TOKEN})"

    # Заменяем строку в .env
    if grep -q "^${VAR_NAME}=" .env 2>/dev/null; then
        sed -i '' "s|^${VAR_NAME}=.*|${VAR_NAME}=${TOKEN}|" .env
        echo "→ ${VAR_NAME} обновлена"
    else
        echo "${VAR_NAME}=${TOKEN}" >> .env
        echo "→ ${VAR_NAME} добавлена"
    fi
    echo ""
    return 0
}

# Бэкап перед любыми изменениями
if [ -f .env ]; then
    cp .env ".env.backup_$(date +%Y%m%d_%H%M%S)"
    echo "→ Бэкап .env сохранён"
    echo ""
fi

case "$CHOICE" in
    1) update_one "WB_TOKEN_READ"   "READ (Статистика + Аналитика + Финансы)" ;;
    2) update_one "WB_TOKEN_ADS"    "ADS (Продвижение)" ;;
    3) update_one "WB_TOKEN_MANAGE" "MANAGE (Контент + Отзывы + Цены)" ;;
    4)
        update_one "WB_TOKEN_READ"   "READ (Статистика + Аналитика + Финансы)"
        update_one "WB_TOKEN_ADS"    "ADS (Продвижение)"
        update_one "WB_TOKEN_MANAGE" "MANAGE (Контент + Отзывы + Цены)"
        ;;
    0|"")
        echo "Выход без изменений."
        read -p "Нажми Enter чтобы закрыть..."
        exit 0
        ;;
    *)
        echo "❌ Непонятный выбор: $CHOICE"
        read -p "Нажми Enter чтобы закрыть..."
        exit 1
        ;;
esac

# ───────────── Проверка через /api/wb/health ─────────────
echo "──────────────────────────────────────────"
echo "→ Проверяю токены через сервер VELA..."

# Сбрасываем кэш WB на сервере (если он есть)
curl -s -X POST http://localhost:8000/api/wb/cache/clear > /dev/null 2>&1

# uvicorn с --reload подхватит изменения .env за пару секунд
sleep 3

RESULT=$(curl -s http://localhost:8000/api/wb/health)
echo ""
echo "Ответ сервера:"
echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"
echo ""

if echo "$RESULT" | grep -q '"ok":true'; then
    echo "════════════════════════════════════════════"
    echo "  ✅ ВСЕ ТОКЕНЫ ЖИВЫЕ. Можно работать."
    echo "════════════════════════════════════════════"
elif echo "$RESULT" | grep -q '"ok":false'; then
    echo "════════════════════════════════════════════"
    echo "  ⚠️  Не все токены прошли. Смотри детали выше."
    echo "  Если 429 — подожди 1-2 мин и проверь ещё раз:"
    echo "     curl http://localhost:8000/api/wb/health"
    echo "════════════════════════════════════════════"
else
    echo "════════════════════════════════════════════"
    echo "  ⚠️  Сервер не отвечает. Запусти VELA_запуск.command."
    echo "════════════════════════════════════════════"
fi

echo ""
read -p "Нажми Enter чтобы закрыть это окно..."
