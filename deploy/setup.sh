#!/usr/bin/env bash
# One-time setup of Annie on a fresh Ubuntu 24.04 VM (Oracle Cloud Always Free, Ampere/ARM).
#
#   bash setup.sh <public-hostname> [login-user] [bcrypt-hash]
#
# <public-hostname>  e.g. 129-146-10-20.sslip.io (resolves to the VM's IP; Caddy gets HTTPS for it)
# [login-user]       optional: protect the whole app with a browser login (HTTP basic auth)
# [bcrypt-hash]      bcrypt hash of that login's password (from `caddy hash-password`)
#
# Re-running is safe: it updates the code and restarts the service.
set -euo pipefail

HOST="${1:?usage: setup.sh <public-hostname> [login-user] [bcrypt-hash]}"
AUTH_USER="${2:-}"
AUTH_HASH="${3:-}"
REPO="${REPO:-https://github.com/ryanteoyx/anniev5.git}"
BRANCH="${BRANCH:-ui-polish}"
APP_HOME=/opt/annie
STREAMLIT_VERSION=1.66.1   # the version the UI was built and tested against

echo "==> System packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git python3-venv python3-pip tesseract-ocr libgl1 libglib2.0-0 caddy iptables-persistent

echo "==> App user and code"
id annie >/dev/null 2>&1 || sudo useradd --system --create-home --home-dir "$APP_HOME" --shell /usr/sbin/nologin annie
if [ -d "$APP_HOME/app/.git" ]; then
    sudo -u annie git -C "$APP_HOME/app" fetch --quiet origin "$BRANCH"
    sudo -u annie git -C "$APP_HOME/app" checkout --quiet "$BRANCH"
    sudo -u annie git -C "$APP_HOME/app" reset --quiet --hard "origin/$BRANCH"
else
    sudo -u annie git clone --quiet --branch "$BRANCH" "$REPO" "$APP_HOME/app"
fi

echo "==> Python environment"
[ -x "$APP_HOME/venv/bin/python" ] || sudo -u annie python3 -m venv "$APP_HOME/venv"
sudo -u annie "$APP_HOME/venv/bin/pip" install --quiet --upgrade pip
sudo -u annie "$APP_HOME/venv/bin/pip" install --quiet -r "$APP_HOME/app/requirements.txt" "streamlit==$STREAMLIT_VERSION"

echo "==> Service"
sudo install -m 644 "$APP_HOME/app/deploy/annie.service" /etc/systemd/system/annie.service
sudo systemctl daemon-reload
sudo systemctl enable --now annie
sudo systemctl restart annie

echo "==> HTTPS reverse proxy (Caddy)"
{
    echo "$HOST {"
    echo "    encode gzip"
    if [ -n "$AUTH_USER" ] && [ -n "$AUTH_HASH" ]; then
        echo "    basicauth {"
        echo "        $AUTH_USER $AUTH_HASH"
        echo "    }"
    fi
    echo "    reverse_proxy 127.0.0.1:8501"
    echo "}"
} | sudo tee /etc/caddy/Caddyfile >/dev/null
sudo systemctl enable --now caddy
sudo systemctl reload caddy || sudo systemctl restart caddy

echo "==> Firewall: allow 80/443 (Oracle images reject everything but SSH by default)"
for port in 80 443; do
    if ! sudo iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
        reject_line=$(sudo iptables -L INPUT --line-numbers | awk '/REJECT/ {print $1; exit}')
        if [ -n "$reject_line" ]; then
            sudo iptables -I INPUT "$reject_line" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
        else
            sudo iptables -A INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT
        fi
    fi
done
sudo netfilter-persistent save >/dev/null

echo "==> Waiting for the app"
for _ in $(seq 1 60); do
    curl -fsS -o /dev/null http://127.0.0.1:8501/_stcore/health && break
    sleep 2
done
curl -fsS http://127.0.0.1:8501/_stcore/health && echo " <- Streamlit healthy"
echo "Done: https://$HOST"
