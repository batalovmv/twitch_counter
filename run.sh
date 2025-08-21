#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# подхват .env (LF-нормализация)
if [ -f .env ]; then
  sed -e 's/\r$//' .env > .env.tmp
  set -a
  # shellcheck disable=SC1091
  source .env.tmp
  set +a
  rm -f .env.tmp
  echo "✅ .env найден: $ROOT_DIR/.env"
else
  echo "ℹ️  .env не найден — переменные будут взяты из окружения"
fi

echo "Bot username: ${TWITCH_BOT_USERNAME:-<empty>}"
echo "Channel: ${TWITCH_CHANNEL:-<empty>}"
echo "YDB endpoint: ${YDB_ENDPOINT:-<empty>}"
echo "YDB database: ${YDB_DATABASE:-<empty>}"
echo "Auth mode: $( [ "${YDB_METADATA_CREDENTIALS:-0}" = "1" ] && echo metadata || echo key/env )"

PYTHONPATH=./src python3 -m bot.main
