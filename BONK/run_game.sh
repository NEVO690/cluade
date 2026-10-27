#!/bin/sh
# BONK! - start the game (Linux / macOS)
cd "$(dirname "$0")"
[ -f .venv/bin/activate ] && . .venv/bin/activate
exec python3 main.py "$@"
