#!/usr/bin/env bash
# Pornire rapidă PostsYT (Linux/macOS)
cd "$(dirname "$0")"
echo "⚡ PostsYT — agentul de postări al lui iSentric"
python3 --version >/dev/null 2>&1 || { echo "Instalează Python 3.10+"; exit 1; }

if [ ! -f data/cookies.json ] && [ ! -f data/cookies.txt ]; then
  echo "➡️  Prima rulare: te loghezi o dată în browser (se deschide singur)."
  python3 -m postsyt login
fi

python3 -m postsyt daemon &
DAEMON_PID=$!
echo "🌐 Dashboard: http://localhost:8787  (Ctrl+C oprește tot)"
python3 -m postsyt dashboard --port 8787
kill $DAEMON_PID 2>/dev/null
