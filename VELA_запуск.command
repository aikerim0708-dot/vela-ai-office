#!/bin/bash
# Двойной клик по этому файлу запускает сервер VELA AI Office.
# Если старый uvicorn уже работает на 8000 — он будет остановлен.

cd "$HOME/Documents/Claude/Projects/ИИ офис/vela-ai-office/backend"

echo "════════════════════════════════════════════"
echo "  VELA AI Office — запуск сервера"
echo "════════════════════════════════════════════"
echo ""

# Останавливаем старый процесс на порту 8000
PIDS=$(lsof -ti:8000 2>/dev/null)
if [ -n "$PIDS" ]; then
    echo "→ Останавливаю старый сервер (PID: $PIDS)..."
    kill -9 $PIDS 2>/dev/null
    sleep 1
fi

# Проверяем .env
echo "→ Проверяю .env..."
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "Закрой это окно, скажи об этом помощнику."
    read -p "Нажми Enter чтобы закрыть..."
    exit 1
fi

PROVIDER=$(grep -E "^VELA_PROVIDER=" .env | cut -d'=' -f2 | tr -d '\r\n ')
if [ "$PROVIDER" = "claude" ]; then
    echo "  ✅ VELA_PROVIDER=claude"
else
    echo "  ⚠️  VELA_PROVIDER=$PROVIDER (нужно claude для Inbox)"
fi

if grep -q "^ANTHROPIC_API_KEY=sk-" .env; then
    echo "  ✅ ANTHROPIC_API_KEY есть"
else
    echo "  ⚠️  ANTHROPIC_API_KEY не настроен"
fi

for T in WB_TOKEN_READ WB_TOKEN_ADS WB_TOKEN_MANAGE; do
    if grep -q "^${T}=eyJ" .env; then
        echo "  ✅ ${T} есть"
    else
        echo "  ⚠️  ${T} не настроен (двойной клик на VELA_обновить_токен.command)"
    fi
done

echo ""
echo "→ Запускаю сервер..."
echo "  Открой в браузере: http://localhost:8000/"
echo ""
echo "  Чтобы остановить сервер — закрой это окно."
echo ""
echo "════════════════════════════════════════════"
echo ""

# Активируем venv и запускаем uvicorn
source .venv/bin/activate
exec uvicorn app:app \
    --port 8000 \
    --host 127.0.0.1 \
    --reload \
    --reload-dir . \
    --reload-exclude ".venv/*" \
    --reload-exclude "data/*" \
    --reload-exclude "__pycache__/*"
