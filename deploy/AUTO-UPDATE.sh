#!/usr/bin/env bash
# Actualizare AUTOMATĂ zilnică (cron) — serverul singular revine singur la zi
# după fiecare push al agentului pe branch-ul de lucru. Zero consolă, veșnic.
set -u
APP=/opt/postsyt/app
BRANCH=arena/01a103b1-postsyt
LOG="/tmp/postsyt-auto-update.log"
{
  echo "── $(date) auto-update ──"
  cd "$APP" || exit 1
  CFG_BAK="$(mktemp)"
  cp config.json "$CFG_BAK" 2>/dev/null || true
  chmod 600 "$CFG_BAK" 2>/dev/null || true
  git fetch -q origin "$BRANCH"
  LOCAL=$(git rev-parse HEAD)
  REMOTE=$(git rev-parse "origin/$BRANCH")
  if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Deja la zi ($LOCAL). Nimic de făcut."
    exit 0
  fi
  echo "Versiune nouă: $LOCAL -> $REMOTE"
  git reset --hard --quiet "origin/$BRANCH"
  cp "$CFG_BAK" config.json && chmod 600 config.json
  /opt/postsyt/venv/bin/pip install -q --no-compile pillow cairosvg 2>/dev/null || true
  rm -f /tmp/postsyt-daemon.pid
  systemctl daemon-reload
  systemctl restart postsyt-dashboard || true
  systemctl restart postsyt-daemon || true   # ULTIMA linie: ne autorestartăm
  echo "✅ Serverul e la zi: $REMOTE"
} >> "$LOG" 2>&1
