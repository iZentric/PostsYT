#!/usr/bin/env bash
# PostsYT — salvare cookie-uri YouTube (export Netscape, din extensia Cookie-Editor)
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DIR/data"
echo "Lipește aici cookie-urile exportate din Cookie-Editor (format Netscape)."
echo "Când termini, apasă Enter și apoi Ctrl+D:"
cat > "$DIR/data/cookies.txt"
echo ""
echo "✅ Salvate în $DIR/data/cookies.txt"
echo "Verificare login: cd $DIR && python3 -m postsyt doctor"
