#!/usr/bin/env bash
# setup.sh — Full setup: venv, SSL cert, Nginx, Gunicorn, systemd
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/venv"
SSL_DIR="/etc/ssl/securechat"
LOG_DIR="/var/log/securechat"

echo ""
echo "▶ SecureChat Setup"
echo "────────────────────────────────────"

# 1. System packages
echo "▶ Installing system packages..."
sudo apt-get update -q
sudo apt-get install -y nginx python3-pip python3-venv openssl

# 2. Virtual environment
echo "▶ Creating virtual environment..."
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q

# 3. .env file
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "▶ Creating .env file..."
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s/change-this-to-a-random-secret-key-32-chars/$SECRET/" "$PROJECT_DIR/.env"
  echo "  ✓ Secret key generated"
fi

# 4. Self-signed SSL certificate
echo "▶ Generating self-signed SSL certificate..."
sudo mkdir -p "$SSL_DIR"
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$SSL_DIR/key.pem" \
  -out "$SSL_DIR/cert.pem" \
  -subj "/CN=securechat-local" \
  -addext "subjectAltName=IP:$(hostname -I | awk '{print $1}')" \
  2>/dev/null
echo "  ✓ SSL cert generated at $SSL_DIR"

# 5. Log directory
echo "▶ Creating log directory..."
sudo mkdir -p "$LOG_DIR"
sudo chown www-data:www-data "$LOG_DIR" 2>/dev/null || true

# 6. Nginx config
echo "▶ Installing Nginx config..."
sudo cp "$PROJECT_DIR/nginx/securechat.conf" /etc/nginx/sites-available/securechat

# Update static path to this project
LOCAL_IP=$(hostname -I | awk '{print $1}')
sudo sed -i "s|/home/narem/securechat|$PROJECT_DIR|g" /etc/nginx/sites-available/securechat

sudo ln -sf /etc/nginx/sites-available/securechat /etc/nginx/sites-enabled/securechat
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx
echo "  ✓ Nginx configured"

# 7. Systemd service
echo "▶ Installing systemd service..."
cat | sudo tee /etc/systemd/system/securechat.service > /dev/null << EOF
[Unit]
Description=SecureChat
After=network.target

[Service]
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$VENV/bin"
ExecStart=$VENV/bin/gunicorn -c $PROJECT_DIR/gunicorn_config.py "run:app"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable securechat
sudo systemctl restart securechat
echo "  ✓ Service started"

echo ""
echo "✅  SecureChat is running!"
echo ""
echo "   From this machine:  https://localhost"
echo "   From other devices: https://$LOCAL_IP"
echo ""
echo "   ⚠  Other devices will see an SSL warning — click 'Advanced → Proceed'"
echo "      This is expected with self-signed certificates."
echo ""
echo "   Logs:   sudo journalctl -u securechat -f"
echo "   Status: sudo systemctl status securechat"
echo "   Stop:   sudo systemctl stop securechat"
