#!/usr/bin/env bash
set -e

# ==========================================================
# Op3nMus1c / Hel1oMus1c Automated Setup & Deployment Script
# Reads parameters directly from music.json
# ==========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/music.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Error: music.json not found in $SCRIPT_DIR!"
    exit 1
fi

echo "🚀 [Op3nMus1c Installer] Loading configuration from music.json..."

# Parse fields using python3 json
PROJECT_NAME=$(python3 -c "import json; f=open('$CONFIG_FILE'); d=json.load(f); print(d.get('project_name', 'Hel1oMus1c'))")
DOMAIN=$(python3 -c "import json; f=open('$CONFIG_FILE'); d=json.load(f); print(d.get('domain', 'hel1o.hel1ow0rld.ru'))")
CORE_HOST=$(python3 -c "import json; f=open('$CONFIG_FILE'); d=json.load(f); print(d.get('api', {}).get('host', '127.0.0.1'))")
CORE_PORT=$(python3 -c "import json; f=open('$CONFIG_FILE'); d=json.load(f); print(d.get('api', {}).get('port', 8001))")
APP_SECRET=$(python3 -c "import json; f=open('$CONFIG_FILE'); d=json.load(f); print(d.get('security', {}).get('app_secret_key', ''))")
MIN_VERSION=$(python3 -c "import json; f=open('$CONFIG_FILE'); d=json.load(f); print(d.get('security', {}).get('min_client_version', '1.0.0'))")

echo "📦 Project: $PROJECT_NAME"
echo "🌐 Domain: $DOMAIN"
echo "🛡️ Core API Port: $CORE_PORT"
echo "🔒 Min Client Version: $MIN_VERSION"

# 1. Install dependencies
echo "📥 [1/5] Installing Python dependencies..."
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    pip install --break-system-packages -q -r "$SCRIPT_DIR/requirements.txt" || pip install -q -r "$SCRIPT_DIR/requirements.txt"
fi

# 2. Ensure directories exist
echo "📁 [2/5] Creating upload and media directories..."
mkdir -p "$SCRIPT_DIR/uploads/track"
mkdir -p "$SCRIPT_DIR/users/avatar"
mkdir -p "$SCRIPT_DIR/users/baner"
mkdir -p "$SCRIPT_DIR/users/badges"

# 3. Create or update SystemD services
echo "⚙️ [3/5] Setting up systemd services..."

# Service: Core Gateway
cat << EOF > /etc/systemd/system/openmusic-core.service
[Unit]
Description=$PROJECT_NAME Core Gateway & Auth API
After=network.target mariadb.service

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 -m uvicorn backend.core.main:app --host $CORE_HOST --port $CORE_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Service: Bot
cat << EOF > /etc/systemd/system/openmusic-bot.service
[Unit]
Description=$PROJECT_NAME Telegram Bot (Secured)
After=network.target mariadb.service

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR/bot
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Service: LRCLIB
cat << EOF > /etc/systemd/system/openmusic-lrc.service
[Unit]
Description=$PROJECT_NAME LRCLIB Lyrics Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR/backend/lrclib
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Service: YouTube Music
cat << EOF > /etc/systemd/system/openmusic-yt.service
[Unit]
Description=$PROJECT_NAME YouTube Music Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR/backend/yt-music
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Service: SoundCloud
cat << EOF > /etc/systemd/system/openmusic-sc.service
[Unit]
Description=$PROJECT_NAME SoundCloud Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR/backend/soundcloud
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# 4. Enable and start services
echo "🔄 [4/5] Enabling and restarting services..."
systemctl enable --now openmusic-core.service
systemctl enable --now openmusic-bot.service
systemctl enable --now openmusic-lrc.service
systemctl enable --now openmusic-yt.service
systemctl enable --now openmusic-sc.service

systemctl restart openmusic-core.service
systemctl restart openmusic-bot.service
systemctl restart openmusic-lrc.service
systemctl restart openmusic-yt.service
systemctl restart openmusic-sc.service

# 5. Configure Nginx
echo "🌍 [5/5] Generating Nginx site configuration..."
NGINX_CONF="/etc/nginx/sites-available/$DOMAIN"

cat << EOF > "$NGINX_CONF"
# Rate limit zone for $PROJECT_NAME API
limit_req_zone \$binary_remote_addr zone=hel1o_api_limit:10m rate=30r/s;

server {
    server_name $DOMAIN;
    client_max_body_size 1024M;
    limit_req zone=hel1o_api_limit burst=50 nodelay;

    # Static media
    location /users/ {
        alias $SCRIPT_DIR/users/;
        expires 30d;
        add_header Access-Control-Allow-Origin *;
    }

    location /uploads/ {
        alias $SCRIPT_DIR/uploads/;
        expires 30d;
        add_header Access-Control-Allow-Origin *;
    }

    # API Security Check
    set \$auth_passed 0;
    if (\$http_x_app_secret = "$APP_SECRET") {
        set \$auth_passed 1;
    }
    if (\$http_user_agent ~* (Hel1oMus1c|Hel1oMus1c-App)) {
        set \$auth_passed 1;
    }

    # LRCLIB API route
    location /api/lyrics {
        if (\$auth_passed = 0) {
            return 403 '{"error": "Forbidden: Access denied. Official Hel1oMus1c client required."}';
        }
        proxy_pass http://127.0.0.1:8012/lyrics;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # New Secure Authentication Gateway (Core)
    location /api/auth/ {
        if (\$auth_passed = 0) {
            return 403 '{"error": "Forbidden: Access denied. Official Hel1oMus1c client required."}';
        }
        proxy_pass http://$CORE_HOST:$CORE_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Main API (Legacy Backend 8000)
    location / {
        if (\$auth_passed = 0) {
            return 403 '{"error": "Forbidden: Access denied. Official Hel1oMus1c client required."}';
        }
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    listen [::]:443 ssl;
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if (\$host = $DOMAIN) {
        return 301 https://\$host\$request_uri;
    }
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    return 404;
}
EOF

ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/$DOMAIN"
nginx -t && systemctl reload nginx

echo "🎉 [Success] $PROJECT_NAME successfully deployed and configured!"
