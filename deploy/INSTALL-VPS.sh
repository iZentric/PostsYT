#!/usr/bin/env bash
# ============================================================================
#  PostsYT — instalare AUTOMATĂ pe server (Ubuntu 22.04 / 24.04 / Debian 12)
#
#  Rulezi pe server (după ce te-ai logat cu SSH):
#     curl -sSL https://raw.githubusercontent.com/iZentric/PostsYT/arena/01a103b1-postsyt/deploy/INSTALL-VPS.sh | sudo bash
#   sau
#     sudo bash INSTALL-VPS.sh
#
#  Ce face: Python + repo + dependinte + servicii systemd (daemon + dashboard)
#  cu repornire automată + token secret pentru dashboard.
#  La final îți arată exact ce mai ai de făcut (cookie-urile).
# ============================================================================
set -euo pipefail

REPO="${REPO:-https://github.com/iZentric/PostsYT.git}"
BRANCH="${BRANCH:-arena/01a103b1-postsyt}"
DIR="${DIR:-/opt/postsyt}"
APP_USER=postsyt
PORT="${PORT:-8787}"
WITH_PLAYWRIGHT="${WITH_PLAYWRIGHT:-0}"   # 1 = sondaje native (descarcă ~500MB chromium)

echo "⚡ PostsYT — instalare server în ${DIR}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl openssl >/dev/null

id -u $APP_USER >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -d "$DIR" -m $APP_USER

# ---- codul
if [ -d "$DIR/app/.git" ]; then
  git -C "$DIR/app" fetch -q origin && git -C "$DIR/app" checkout -q "$BRANCH" && git -C "$DIR/app" pull -q
else
  if ! git clone -q -b "$BRANCH" "$REPO" "$DIR/app" 2>/dev/null; then
    echo ""
    echo "❌ Nu am putut clona repo-ul (e privat?). Upload-u-l manual:"
    echo "   pe PC:  scp PostsYT.zip root@IP-UL-SERVERULUI:/root/"
    echo "   apoi aici:  apt install unzip -y && mkdir -p $DIR/app && unzip -o PostsYT.zip -d $DIR/app --strip-components=1"
    echo "   și re-rulează acest script."
    exit 1
  fi
fi

# ---- python venv + dependinte
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q --upgrade pip
"$DIR/venv/bin/pip" install -q pillow cairosvg
if [ "$WITH_PLAYWRIGHT" = "1" ]; then
  "$DIR/venv/bin/pip" install -q playwright
  "$DIR/venv/bin/playwright" install --with-deps chromium
fi

# ---- config + token secret
cd "$DIR/app"
mkdir -p data
if [ ! -f config.json ]; then cp config.example.json config.json; fi
TOKEN="$(openssl rand -hex 16)"
python3 - "$TOKEN" <<'PY'
import json, sys
cfg = json.load(open("config.json", encoding="utf-8"))
cfg["dashboard_token"] = sys.argv[1]
json.dump(cfg, open("config.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
PY
chmod 600 config.json 2>/dev/null || true

# ---- servicii systemd
PYBIN="$DIR/venv/bin/python"
cat > /etc/systemd/system/postsyt-daemon.service <<UNIT
[Unit]
Description=PostsYT Agent (daemon)
After=network-online.target
Wants=network-online.target
[Service]
User=root
WorkingDirectory=$DIR/app
ExecStart=$PYBIN -m postsyt daemon
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/postsyt-dashboard.service <<UNIT
[Unit]
Description=PostsYT Dashboard (web)
After=network-online.target
Wants=network-online.target
[Service]
User=root
WorkingDirectory=$DIR/app
ExecStart=$PYBIN -m postsyt dashboard --port $PORT
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now postsyt-dashboard.service postsyt-daemon.service >/dev/null 2>&1 || true
systemctl restart postsyt-dashboard.service postsyt-daemon.service

IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')
echo ""
echo "════════════════════════════════════════════════════════════════"
echo " ✅ PostsYT rulează acum 24/7 pe acest server!"
echo ""
echo " 🌐 Dashboardul TĂU (secret, nu-l da nimănui):"
echo "      http://$IP:$PORT/?key=$TOKEN"
echo ""
echo " 📋 ULTIMUL PAS — cookie-urile YouTube (3 minute, de pe PC-ul tău):"
echo "    1. în browserul unde ești logat pe canal: instalează extensia"
echo "       Cookie-Editor → deschide youtube.com → Export → „Netscape”"
echo "    2. aici pe server rulează:"
echo "       bash $DIR/app/deploy/install-cookies.sh"
echo "       și lipește textul exportat (apoi apasă Ctrl+D)"
echo "    3. verifică:  $PYBIN -m postsyt doctor   (din $DIR/app)"
echo ""
echo " 🔎 Comenzi utile:"
echo "    systemctl status postsyt-daemon    # starea agentului"
echo "    journalctl -u postsyt-daemon -f    # log live"
echo "    systemctl restart postsyt-daemon"
echo "════════════════════════════════════════════════════════════════"
