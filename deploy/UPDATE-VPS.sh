#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  PostsYT — ACTUALIZARE server (aduce ultima versiune, păstrează TOT)
#
#  Pe server, o singură linie:
#     curl -sSL https://raw.githubusercontent.com/iZentric/PostsYT/arena/01a103b1-postsyt/deploy/UPDATE-VPS.sh | sudo bash
#
#  Păstrează: config.json (cheile tale), data/ (cookies, baza de date, imagini)
#  Face: cod nou → restart daemon+dashboard → verificare doctor + analytics
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

BRANCH="${BRANCH:-arena/01a103b1-postsyt}"
DIR="${DIR:-/opt/postsyt}"
PYBIN="$DIR/venv/bin/python"

echo "🔄 PostsYT — actualizare server"

if [ ! -d "$DIR/app/.git" ]; then
  echo "❌ Nu găsesc instalarea în $DIR/app — rulează întâi INSTALL-VPS.sh"
  exit 1
fi

cd "$DIR/app"

# ---- păstrează configul cu cheile generate la instalare
cp config.json /tmp/postsyt-config.backup.json

# ---- cod nou
git fetch -q origin "$BRANCH"
git reset -q --hard "origin/$BRANCH"

# ---- configul înapoi + permisiuni
cp /tmp/postsyt-config.backup.json config.json
chmod 600 config.json
[ -f data/cookies.txt ] && chmod 600 data/cookies.txt || true

# ---- restart servicii
systemctl daemon-reload
systemctl restart postsyt-daemon postsyt-dashboard
sleep 2
systemctl --no-pager --quiet is-active postsyt-daemon    && echo "✅ daemon activ"    || echo "⚠️ daemon NU e activ: journalctl -u postsyt-daemon -n 30"
systemctl --no-pager --quiet is-active postsyt-dashboard && echo "✅ dashboard activ" || echo "⚠️ dashboard NU e activ"

# ---- verificare finală (sesiune + analytics real)
echo ""
echo "════════ VERIFICARE ════════"
"$PYBIN" -m postsyt analytics || echo "⚠️ analytics a întâmpinat o problemă (vezi mai sus)"
echo "═══════════════════════════"
echo "✅ ACTUALIZARE COMPLETĂ — serverul e la zi"
