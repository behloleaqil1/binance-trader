#!/usr/bin/env bash
# Runs ON THE VPS as root. Idempotent. Fully isolated from purocoach:
# dedicated user/dir/venv/service + a NEW nginx site. Never touches
# purocoach's service, sites, or databases.
set -euo pipefail

APP=/opt/binance-trader
RUN_CERTBOT="${1:-false}"
ADMIN_EMAIL="behloleaqil@gmail.com"
DOMAIN="api.bot.behloleaqil.com"
CORS_ORIGIN="https://bot.behloleaqil.com"

echo "==> user + dirs"
id botrunner >/dev/null 2>&1 || useradd -r -m -d "$APP" -s /usr/sbin/nologin botrunner
install -d -o botrunner -g botrunner "$APP/app/backend/data"

echo "==> system packages"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip >/dev/null

echo "==> venv + deps"
if [ ! -d "$APP/venv" ]; then
  python3 -m venv "$APP/venv"
  chown -R botrunner:botrunner "$APP/venv"
fi
sudo -u botrunner "$APP/venv/bin/pip" install -q --upgrade pip
sudo -u botrunner "$APP/venv/bin/pip" install -q -r "$APP/app/backend/requirements.txt"

echo "==> .env (created once, preserved on redeploys)"
ENV="$APP/app/.env"
if [ ! -f "$ENV" ]; then
  PW=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)
  {
    echo "TESTNET=false"
    echo "BINANCE_API_KEY="
    echo "BINANCE_API_SECRET="
    echo "API_HOST=127.0.0.1"
    echo "API_PORT=8100"
    echo "AUTH_USERNAME=admin"
    echo "AUTH_PASSWORD=$PW"
    echo "DB_PATH=data/bot.db"
    echo "LOG_LEVEL=INFO"
    echo "CORS_ORIGINS=$CORS_ORIGIN"
  } > "$ENV"
  chown botrunner:botrunner "$ENV"
  chmod 600 "$ENV"
  echo "GENERATED_ADMIN_PASSWORD=$PW"
else
  echo "existing .env preserved"
fi

echo "==> systemd service"
install -m 644 "$APP/app/deploy/binance-trader.service" /etc/systemd/system/binance-trader.service
systemctl daemon-reload
systemctl enable binance-trader >/dev/null 2>&1 || true
systemctl restart binance-trader
sleep 4
systemctl is-active binance-trader >/dev/null && curl -sf http://127.0.0.1:8100/api/health >/dev/null \
  && echo "backend-up" || { echo "BACKEND FAILED"; journalctl -u binance-trader -n 30 --no-pager; exit 1; }

echo "==> nginx site (new file; purocoach sites untouched)"
if [ ! -f /etc/nginx/sites-available/bot-api ]; then
  install -m 644 "$APP/app/deploy/nginx-bot-api.conf" /etc/nginx/sites-available/bot-api
  ln -sf /etc/nginx/sites-available/bot-api /etc/nginx/sites-enabled/bot-api
fi
nginx -t && systemctl reload nginx && echo "nginx reloaded (graceful; purocoach kept serving)"

if [ "$RUN_CERTBOT" = "true" ]; then
  echo "==> certbot for $DOMAIN"
  which certbot >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$ADMIN_EMAIL" --redirect \
    && { nginx -t && systemctl reload nginx; echo "https-ready"; } \
    || echo "certbot skipped/failed — is DNS for $DOMAIN live yet?"
fi
echo "==> done"
