#!/bin/bash
# provision_server.sh — разворачивает VELA Office на свежем Ubuntu 22.04.
# Запускается НА СЕРВЕРЕ от root. Код уже должен лежать в /opt/vela-ai-office
# (его кладёт deploy.command через rsync с мака). GitHub не нужен.
#
# HTTPS: через бесплатный домен nip.io (<ip>.nip.io) + Let's Encrypt — без покупки домена.
#
# Переменные (можно передать через env):
#   VELA_DOMAIN  — домен для HTTPS, по умолчанию <публичный_ip>.nip.io
#   CERT_EMAIL   — email для Let's Encrypt
set -euo pipefail

APP_DIR="/opt/vela-ai-office"
BACKEND="${APP_DIR}/backend"
VELA_USER="vela"
PUB_IP="$(curl -s --max-time 10 https://api.ipify.org || echo '')"
VELA_DOMAIN="${VELA_DOMAIN:-${PUB_IP}.nip.io}"
CERT_EMAIL="${CERT_EMAIL:-aikerim0708@gmail.com}"

G='\033[0;32m'; Y='\033[1;33m'; N='\033[0m'
log(){ echo -e "${G}[provision]${N} $*"; }
warn(){ echo -e "${Y}[provision]${N} $*"; }

[ "$(id -u)" -eq 0 ] || { echo "Запускать от root"; exit 1; }

log "Публичный IP: ${PUB_IP}, домен: ${VELA_DOMAIN}"

# ── 1. пакеты ──
log "1/7 Устанавливаю пакеты (python, nginx, certbot)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip \
    nginx certbot python3-certbot-nginx \
    curl build-essential libssl-dev libffi-dev >/dev/null

# ── 2. пользователь vela ──
log "2/7 Пользователь ${VELA_USER}..."
id "${VELA_USER}" &>/dev/null || useradd -m -s /bin/bash "${VELA_USER}"
chown -R "${VELA_USER}:${VELA_USER}" "${APP_DIR}"

# ── 3. venv + зависимости ──
log "3/7 Python venv + зависимости (может занять пару минут)..."
sudo -u "${VELA_USER}" bash <<EOF
set -e
cd "${BACKEND}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
EOF

# ── 4. .env проверка ──
if [ ! -f "${BACKEND}/.env" ]; then
    warn ".env не найден — создаю заготовку. Заполни токены!"
    cat > "${BACKEND}/.env" <<'ENVEOF'
VELA_PROVIDER=claude
ANTHROPIC_API_KEY=PUT_YOUR_KEY
VELA_MODEL=claude-sonnet-4-5
WB_TOKEN_READ=PUT_YOUR_TOKEN
WB_TOKEN_ADS=PUT_YOUR_TOKEN
WB_TOKEN_MANAGE=PUT_YOUR_TOKEN
WB_API_TOKEN=PUT_YOUR_TOKEN
TELEGRAM_BOT_TOKEN=
ALLOWED_TELEGRAM_USER_IDS=
ENVEOF
fi
chown "${VELA_USER}:${VELA_USER}" "${BACKEND}/.env"
chmod 600 "${BACKEND}/.env"

# ── 5. systemd: веб + отчёты (бот включим позже, когда будет токен) ──
log "4/7 systemd-сервисы..."
cat > /etc/systemd/system/vela.service <<EOF
[Unit]
Description=VELA AI Office
After=network.target
[Service]
Type=simple
User=${VELA_USER}
WorkingDirectory=${BACKEND}
EnvironmentFile=${BACKEND}/.env
ExecStart=${BACKEND}/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

for kind in daily weekly monthly; do
cat > /etc/systemd/system/vela-${kind}.service <<EOF
[Unit]
Description=VELA ${kind} report
After=vela.service
[Service]
Type=oneshot
User=${VELA_USER}
WorkingDirectory=${BACKEND}
EnvironmentFile=${BACKEND}/.env
ExecStart=${BACKEND}/.venv/bin/python scripts/generate_${kind}.py
StandardOutput=append:/var/log/vela-${kind}.log
StandardError=append:/var/log/vela-${kind}.log
EOF
done

cat > /etc/systemd/system/vela-daily.timer <<EOF
[Unit]
Description=Vela Daily 07:00
[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/vela-weekly.timer <<EOF
[Unit]
Description=Vela Weekly Sun 21:00
[Timer]
OnCalendar=Sun *-*-* 21:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/vela-monthly.timer <<EOF
[Unit]
Description=Vela Monthly 1st 09:00
[Timer]
OnCalendar=*-*-01 09:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable vela.service vela-daily.timer vela-weekly.timer vela-monthly.timer >/dev/null 2>&1
systemctl restart vela.service

# ── 6. nginx ──
log "5/7 nginx (домен ${VELA_DOMAIN})..."
cat > /etc/nginx/sites-available/vela <<EOF
server {
    listen 80;
    server_name ${VELA_DOMAIN} ${PUB_IP};
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
        proxy_read_timeout 300s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/vela /etc/nginx/sites-enabled/vela
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 7. фаервол + HTTPS ──
log "6/7 Фаервол (22/80/443)..."
if command -v ufw >/dev/null; then
    ufw allow 22/tcp >/dev/null 2>&1 || true
    ufw allow 2222/tcp >/dev/null 2>&1 || true
    ufw allow 80/tcp >/dev/null 2>&1 || true
    ufw allow 443/tcp >/dev/null 2>&1 || true
    echo "y" | ufw enable >/dev/null 2>&1 || true
fi

log "7/7 HTTPS-сертификат Let's Encrypt для ${VELA_DOMAIN}..."
if certbot --nginx -d "${VELA_DOMAIN}" --non-interactive --agree-tos -m "${CERT_EMAIL}" --redirect >/tmp/certbot.log 2>&1; then
    log "HTTPS выпущен ✅"
else
    warn "HTTPS не выпустился автоматически (см. /tmp/certbot.log). Сайт работает по http, поправим вручную."
fi

echo ""
echo "════════════════════════════════════════════"
echo -e "${G}  ✅ VELA Office развёрнут${N}"
echo "════════════════════════════════════════════"
echo "Проверка:   curl -s http://127.0.0.1:8000/api/health"
echo "Снаружи:    https://${VELA_DOMAIN}/"
echo "Логи веба:  journalctl -u vela -f"
echo "Mini App URL для @BotFather:  https://${VELA_DOMAIN}/"
systemctl is-active vela.service >/dev/null && echo "Сервис vela: АКТИВЕН" || echo "Сервис vela: НЕ запустился — смотри journalctl -u vela"
