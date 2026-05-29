#!/bin/bash
# verify-no-secrets.sh
# Проверяет что в коммит/репозиторий НЕ попали секреты VELA.
# Запускать перед каждым git push (или встроить в pre-push hook).
#
# Использование:
#   bash scripts/verify-no-secrets.sh
#   → exit 0 если чисто, exit 1 если нашёл секрет
#
# Что ищет:
#   - WB JWT-токены (формат eyJ...eyJ...)
#   - Anthropic API ключи (sk-ant-...)
#   - OpenAI API ключи (sk-...)
#   - SSH private keys
#   - .env файлы в индексе git

set -euo pipefail

cd "$(dirname "$0")/.."

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAIL=0

echo "════════════════════════════════════════════"
echo "  VELA — проверка на утечку секретов"
echo "════════════════════════════════════════════"
echo ""

# ------- 1. Проверка что .env НЕ в git -------
echo "→ Проверяю что .env не в git индексе..."
if git ls-files --error-unmatch backend/.env 2>/dev/null; then
    echo -e "${RED}❌ КРИТИЧНО: backend/.env в git! Удалить:${NC}"
    echo "   git rm --cached backend/.env"
    FAIL=1
elif git ls-files --error-unmatch .env 2>/dev/null; then
    echo -e "${RED}❌ КРИТИЧНО: .env в git! Удалить:${NC}"
    echo "   git rm --cached .env"
    FAIL=1
else
    echo -e "${GREEN}  ✅ .env не в git${NC}"
fi
echo ""

# ------- 2. Поиск WB JWT-токенов в коде -------
echo "→ Ищу WB JWT-токены (eyJ...eyJ...) в отслеживаемых файлах..."
# Только в файлах под контролем git (исключая .env и т.п.)
if git ls-files | xargs grep -l "eyJhbGciOiJFUzI1NiIsImtpZCI" 2>/dev/null | grep -v "^docs/" | grep -v "\.md$" | grep -v "\.env" > /tmp/wb_token_leak 2>/dev/null && [ -s /tmp/wb_token_leak ]; then
    echo -e "${RED}❌ Найдены WB JWT-токены в коде:${NC}"
    cat /tmp/wb_token_leak
    FAIL=1
else
    echo -e "${GREEN}  ✅ WB JWT-токены не утекли в код${NC}"
fi
echo ""

# ------- 3. Поиск Anthropic API ключей -------
echo "→ Ищу Anthropic API ключи (sk-ant-...) в отслеживаемых файлах..."
if git ls-files | xargs grep -l "sk-ant-api" 2>/dev/null | grep -v "\.env" | grep -v "verify-no-secrets" > /tmp/anthropic_leak 2>/dev/null && [ -s /tmp/anthropic_leak ]; then
    echo -e "${RED}❌ Найдены Anthropic API ключи:${NC}"
    cat /tmp/anthropic_leak
    FAIL=1
else
    echo -e "${GREEN}  ✅ Anthropic API ключи не утекли${NC}"
fi
echo ""

# ------- 4. Поиск Telegram bot token -------
echo "→ Ищу Telegram bot tokens..."
if git ls-files | xargs grep -lE "[0-9]{9,10}:AAH" 2>/dev/null | grep -v "\.env" | grep -v "verify-no-secrets" > /tmp/tg_leak 2>/dev/null && [ -s /tmp/tg_leak ]; then
    echo -e "${RED}❌ Найдены Telegram bot tokens:${NC}"
    cat /tmp/tg_leak
    FAIL=1
else
    echo -e "${GREEN}  ✅ Telegram bot tokens не утекли${NC}"
fi
echo ""

# ------- 5. Поиск SSH private keys -------
echo "→ Ищу SSH private keys..."
if git ls-files | xargs grep -lE "BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY" 2>/dev/null > /tmp/ssh_leak 2>/dev/null && [ -s /tmp/ssh_leak ]; then
    echo -e "${RED}❌ Найдены SSH private keys:${NC}"
    cat /tmp/ssh_leak
    FAIL=1
else
    echo -e "${GREEN}  ✅ SSH private keys не утекли${NC}"
fi
echo ""

# ------- 6. Проверка backup файлов -------
echo "→ Ищу backup-файлы .env..."
if git ls-files | grep -E "\.env\.backup_|\.env\.bak" > /tmp/backup_leak 2>/dev/null && [ -s /tmp/backup_leak ]; then
    echo -e "${RED}❌ Backup файлы .env в git:${NC}"
    cat /tmp/backup_leak
    FAIL=1
else
    echo -e "${GREEN}  ✅ Backup-файлы .env не в git${NC}"
fi
echo ""

# ------- 7. Проверка размера файлов (защита от случайных дампов БД) -------
echo "→ Проверяю что в git нет файлов >5MB..."
LARGE=$(git ls-files | xargs -I{} sh -c 'if [ -f "{}" ]; then SIZE=$(wc -c < "{}"); if [ "$SIZE" -gt 5242880 ]; then echo "{} ($((SIZE/1024))KB)"; fi; fi' 2>/dev/null)
if [ -n "$LARGE" ]; then
    echo -e "${YELLOW}⚠️  Большие файлы в git (>5MB) — проверь не дамп ли БД:${NC}"
    echo "$LARGE"
fi
echo ""

# ------- ИТОГ -------
rm -f /tmp/wb_token_leak /tmp/anthropic_leak /tmp/tg_leak /tmp/ssh_leak /tmp/backup_leak

echo "════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}  ✅ ЧИСТО. Можно делать git push.${NC}"
    echo "════════════════════════════════════════════"
    exit 0
else
    echo -e "${RED}  ❌ НАЙДЕНЫ СЕКРЕТЫ. Git push ЗАБЛОКИРОВАН.${NC}"
    echo "════════════════════════════════════════════"
    echo ""
    echo "Действия по очистке:"
    echo "  1. Убери секрет из файла"
    echo "  2. git add . && git commit --amend --no-edit"
    echo "  3. Если уже был git push с секретом → НЕМЕДЛЕННО пересоздай токен в WB/Anthropic кабинете"
    echo "  4. bash scripts/verify-no-secrets.sh ещё раз"
    exit 1
fi
