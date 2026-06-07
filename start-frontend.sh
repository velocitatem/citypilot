#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/apps/webapp"

if ! command -v bun &>/dev/null; then
  echo "bun not found — installing..."
  curl -fsSL https://bun.sh/install | bash
  export PATH="$HOME/.bun/bin:$PATH"
fi

if [ ! -d node_modules ]; then
  echo "Installing dependencies..."
  bun install
fi

exec bun run dev
