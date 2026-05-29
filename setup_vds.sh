#!/bin/bash
# setup_vds.sh
# Один раз запускается на свежем VDS Ubuntu 22.04 для развёртывания VELA Office.
#
# Запуск:
#   ssh root@<IP>
#   bash <(curl -sSL https://raw.githubusercontent.com/aikerim0708/vela-ai-office/main/scripts/setup_vds.sh)
#
# Что делает:
#   1. Создаёт пользователя vela (не root)
#   2. Настраивает SSH only-key, фаервол ufw
#   3. Ставит Python 3.9, nginx, git, certbot
#   4. Клонит репо через deploy key
#   5. Создаёт systemd service для uvicorn
#   6. Настраивает nginx + HTTPS через Let's Encrypt
#   7. Cron для nightly sync в GitHub
#
# ⚠️ ПЕРЕД ЗАПУСКОМ:
#   - убедись что у тебя есть SSH-доступ к серверу (root)
#   - убедись что есть GitHub deploy key для приватного репо
#   - .env будет создан пустым, заполнить вручную через scp

set -euo pipefail

# ────────── переменные ──────────
VELA_USER="vela"
VELA_HOME="/home/vela"
REPO_URL="git@github.com:aikerim0708/vela-ai-office.git"  # обновить после создания репо
APP_DIR="${VELA_HOME}/vela-ai-office"
SERVER_NAME="${VELA_DOMAIN:-_}"  # передать через env или _ (любой host)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[setup-vds]${NC} $*"; }
warn() { echo -e "${YELLOW}[setup-vds]${NC} $*"; }
err() { echo -e "${RED}[setup-vds]${NC} $*" >&2; }

# ────────── проверки ──────────
if [ "$(id -u)" -ne 0 ]; then
    err "Запускать от root. Используй: sudo bash setup_vds.sh"
    exit 1
fi

if ! grep -q "Ubuntu" /etc/os-release; then
    warn "Этот скрипт тестировался только на Ubuntu 22.04. Продолжаем на свой страх."
fi

# ────────── 1. Базовая безопасность ──────────
log "1/7 Создаю пользователя ${VELA_USER}..."
if ! id "${VELA_USER}" &>/dev/null; then
    useradd -m -s /bin/bash "${VELA_USER}"
    usermod -aG sudo "${VELA_USER}"
fi

# Копируем SSH-ключи root для пользователя vela
mkdir -p "${VELA_HOME}/.ssh"
if [ -f /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys "${VELA_HOME}/.ssh/authorized_keys"
    chown -R "${VELA_USER}:${VELA_USER}" "${VELA_HOME}/.ssh"
    chmod 700 "${VELA_HOME}/.ssh"
    chmod 600 "${VELA_HOME}/.ssh/authorized_keys"
fi

log "2/7 Настройка SSH: только ключ, без пароля..."
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
systemctl reload sshd

log "3/7 Установка фаервола ufw..."
apt-get update -qq
apt-get install -y -qq ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
echo "y" | ufw enable

# ────────── 2. Зависимости ──────────
log "4/7 Установка Python 3.9, nginx, git, certbot..."
apt-get install -y -qq software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa || true
apt-get update -qq
apt-get install -y -qq \
    python3.9 python3.9-venv python3.9-dev python3-pip \
    nginx git curl wget htop \
    certbot python3-certbot-nginx \
    build-essential libssl-dev libffi-dev

# ────────── 3. Клон репо ──────────
log "5/7 Клонирование репозитория VELA..."
sudo -u "${VELA_USER}" bash <<EOF
set -e
cd "${VELA_HOME}"

# проверка SSH доступа к GitHub
if ! ssh -T -o StrictHostKeyChecking=accept-new git@github.com 2>&1 | grep -q "successfully authenticated"; then
    echo ""
    echo "⚠️  GitHub SSH не настроен."
    echo "Чтобы продолжить:"
    echo "1. На локальной машине: cat ~/.ssh/id_ed25519"
    echo "2. На сервере: scp в ~/.ssh/id_ed25519 или создать deploy key через GitHub UI"
    echo "3. Запустить скрипт повторно"
    exit 1
fi

if [ ! -d "${APP_DIR}" ]; then
    git clone "${REPO_URL}" "${APP_DIR}"
else
    cd "${APP_DIR}" && git pull --ff-only
fi
EOF

# ────────── 4. Python venv + зависимости ──────────
log "6/7 Установка Python venv и зависимостей..."
sudo -u "${VELA_USER}" bash <<EOF
set -e
cd "${APP_DIR}/backend"
python3.9 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
EOF

# .env шаблон (заполнить вручную через scp)
if [ ! -f "${APP_DIR}/backend/.env" ]; then
    cat > "${APP_DIR}/backend/.env" <<'ENVEOF'
VELA_PROVIDER=claude
ANTHROPIC_API_KEY=PUT_YOUR_KEY
VELA_MODEL=claude-sonnet-4-5
WB_TOKEN_READ=PUT_YOUR_TOKEN
WB_TOKEN_ADS=PUT_YOUR_TOKEN
WB_TOKEN_MANAGE=PUT_YOUR_TOKEN
WB_API_TOKEN=PUT_YOUR_TOKEN
TELEGRAM_BOT_TOKEN=PUT_YOUR_BOT_TOKEN
ALLOWED_TELEGRAM_USER_IDS=PUT_YOUR_USER_ID
ENVEOF
    chown "${VELA_USER}:${VELA_USER}" "${APP_DIR}/backend/.env"
    chmod 600 "${APP_DIR}/backend/.env"
    warn ".env создан пустым. Заполнить токены через scp с локальной машины."
fi

# ────────── 5. systemd service ──────────
log "7/7 Настройка systemd service..."
cat > /etc/systemd/system/vela.service <<EOF
[Unit]
Description=VELA AI Office
After=network.target

[Service]
Type=simple
User=${VELA_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="PATH=${APP_DIR}/backend/.venv/bin"
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${APP_DIR}/backend/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/vela-bot.service <<EOF
[Unit]
Description=VELA Telegram Bot
After=network.target vela.service
Requires=vela.service

[Service]
Type=simple
User=${VELA_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="PATH=${APP_DIR}/backend/.venv/bin"
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${APP_DIR}/backend/.venv/bin/python telegram_bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/vela-daily.service <<EOF
[Unit]
Description=VELA Daily Report Generator
After=vela.service
Requires=vela.service

[Service]
Type=oneshot
User=${VELA_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="PATH=${APP_DIR}/backend/.venv/bin"
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${APP_DIR}/backend/.venv/bin/python scripts/generate_daily.py
StandardOutput=append:/var/log/vela-daily.log
StandardError=append:/var/log/vela-daily.log
EOF

cat > /etc/systemd/system/vela-daily.timer <<EOF
[Unit]
Description=Запуск Vela Daily в 07:00 ежедневно

[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true
Unit=vela-daily.service

[Install]
WantedBy=timers.target
EOF

# ---------- Weekly Service + Timer (воскресенье 21:00) ----------
cat > /etc/systemd/system/vela-weekly.service <<EOF
[Unit]
Description=VELA Weekly Report Generator
After=vela.service
Requires=vela.service

[Service]
Type=oneshot
User=${VELA_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="PATH=${APP_DIR}/backend/.venv/bin"
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${APP_DIR}/backend/.venv/bin/python scripts/generate_weekly.py
StandardOutput=append:/var/log/vela-weekly.log
StandardError=append:/var/log/vela-weekly.log
EOF

cat > /etc/systemd/system/vela-weekly.timer <<EOF
[Unit]
Description=Запуск Vela Weekly в воскресенье 21:00

[Timer]
OnCalendar=Sun *-*-* 21:00:00
Persistent=true
Unit=vela-weekly.service

[Install]
WantedBy=timers.target
EOF

# ---------- Monthly Finance Service + Timer (1-е число 09:00) ----------
cat > /etc/systemd/system/vela-monthly.service <<EOF
[Unit]
Description=VELA Monthly Finance Report Generator
After=vela.service
Requires=vela.service

[Service]
Type=oneshot
User=${VELA_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="PATH=${APP_DIR}/backend/.venv/bin"
EnvironmentFile=${APP_DIR}/backend/.env
ExecStart=${APP_DIR}/backend/.venv/bin/python scripts/generate_monthly.py
StandardOutput=append:/var/log/vela-monthly.log
StandardError=append:/var/log/vela-monthly.log
EOF

cat > /etc/systemd/system/vela-monthly.timer <<EOF
[Unit]
Description=Запуск Vela Monthly Finance 1-го числа в 09:00

[Timer]
OnCalendar=*-*-01 09:00:00
Persistent=true
Unit=vela-monthly.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable vela.service vela-bot.service vela-daily.timer vela-weekly.timer vela-monthly.timer

# ────────── 6. nginx ──────────
cat > /etc/nginx/sites-available/vela <<EOF
server {
    listen 80;
    server_name ${SERVER_NAME};

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
    }
}
EOF

ln -sf /etc/nginx/sites-available/vela /etc/nginx/sites-enabled/vela
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ────────── ИТОГ ──────────
echo ""
echo "════════════════════════════════════════════"
echo -e "${GREEN}  ✅ VDS установлен.${NC}"
echo "════════════════════════════════════════════"
echo ""
echo "Следующие шаги (вручную):"
echo "1. Заполнить ${APP_DIR}/backend/.env через scp с локалки:"
echo "   scp '/Users/aikerimturgunbaeva/Documents/Claude/Projects/ИИ офис/vela-ai-office/backend/.env' ${VELA_USER}@<IP>:${APP_DIR}/backend/.env"
echo ""
echo "2. Запустить сервис:"
echo "   ssh ${VELA_USER}@<IP> 'sudo systemctl start vela'"
echo ""
echo "3. Проверить логи:"
echo "   ssh ${VELA_USER}@<IP> 'sudo journalctl -u vela -f'"
echo ""
echo "4. Если есть домен — настроить HTTPS:"
echo "   ssh root@<IP> 'certbot --nginx -d vela.example.com'"
echo ""
echo "5. Открыть в браузере: http://<IP>/api/health"
echo ""
