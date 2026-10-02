#!/usr/bin/env bash
# Naukri Auto Updater - basic CLI server setup (Ubuntu/Debian)
# Usage: sudo bash server_setup.sh
# Installs: Python venv, lightweight deps (curl-cffi, NO browser), systemd service OR cron
set -e

APP_DIR="/opt/naukriauto"
SERVICE_NAME="naukri-auto"

echo "==> Installing system deps..."
apt-get update
apt-get install -y python3 python3-venv python3-pip cron tzdata

echo "==> Creating $APP_DIR ..."
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR/" 2>/dev/null || true
cd "$APP_DIR"

echo "==> Python venv..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
# No browser needed: login uses lightweight curl-cffi (Chrome TLS impersonation)

echo "==> .env check..."
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from example - EDIT IT NOW: nano $APP_DIR/.env"
fi

echo "==> Sanity check (no secrets printed)..."
./venv/bin/python main.py --check || true

echo ""
echo "Choose run mode:"
echo "  [1] systemd always-on (scheduler 09:00 + 12:30, recommended)"
echo "  [2] cron one-shots (runs only at 9:00 AM + 12:30 PM IST)"
read -rp "Enter 1 or 2 [1]: " MODE
MODE="${MODE:-1}"

if [ "$MODE" = "2" ]; then
  echo "==> Installing cron jobs (Asia/Kolkata)..."
  # Server TZ to IST so 9:00/12:30 match Naukri recruiter hours
  timedatectl set-timezone Asia/Kolkata || true
  CRON_TMP="$(mktemp)"
  crontab -l 2>/dev/null | grep -v "naukriauto.*main.py --update-now" > "$CRON_TMP" || true
  echo "0 9 * * * /opt/naukriauto/venv/bin/python /opt/naukriauto/main.py --update-now >> /opt/naukriauto/data/cron.log 2>&1" >> "$CRON_TMP"
  echo "30 12 * * * /opt/naukriauto/venv/bin/python /opt/naukriauto/main.py --update-now >> /opt/naukriauto/data/cron.log 2>&1" >> "$CRON_TMP"
  crontab "$CRON_TMP"
  rm -f "$CRON_TMP"
  echo "Cron installed. Verify with: crontab -l"
else
  echo "==> Installing systemd service..."
  timedatectl set-timezone Asia/Kolkata || true
  cp naukri-auto.service /etc/systemd/system/${SERVICE_NAME}.service
  # Run as the invoking non-root user if possible
  RUN_USER="${SUDO_USER:-root}"
  sed -i "s/^User=.*/User=${RUN_USER}/" /etc/systemd/system/${SERVICE_NAME}.service
  systemctl daemon-reload
  systemctl enable --now ${SERVICE_NAME}
  echo "Service started. Logs: journalctl -u ${SERVICE_NAME} -f"
fi

echo ""
echo "Test manually with:"
echo "  /opt/naukriauto/venv/bin/python /opt/naukriauto/main.py --headline"
echo "  /opt/naukriauto/venv/bin/python /opt/naukriauto/main.py --update-now"
