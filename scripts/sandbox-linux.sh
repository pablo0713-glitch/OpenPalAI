#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

ENGINE="${ENGINE:-podman}"
SANDBOX_DIR="${SANDBOX_DIR:-./.sandbox/linux}"
SANDBOX_BIND="${SANDBOX_BIND:-127.0.0.1:18080}"

mkdir -p "$SANDBOX_DIR/data/library" "$SANDBOX_DIR/cache"

if [ ! -f "$SANDBOX_DIR/.env" ]; then
  if [ -f ".env" ]; then
    cp .env "$SANDBOX_DIR/.env"
  else
    cat > "$SANDBOX_DIR/.env" <<'EOF'
# Sandbox configuration. Fill this through /setup or edit directly.
MODEL_PROVIDER=anthropic
SL_BRIDGE_HOST=0.0.0.0
SL_BRIDGE_PORT=8080
EOF
  fi
fi

if [ -d "data/library" ] && [ -z "$(find "$SANDBOX_DIR/data/library" -maxdepth 1 -type f -name '*.md' -print -quit)" ]; then
  cp data/library/*.md "$SANDBOX_DIR/data/library/" 2>/dev/null || true
fi

export SANDBOX_DIR SANDBOX_BIND

case "${1:-up}" in
  up)
    "$ENGINE" compose -f compose.sandbox.yml up -d --build
    echo "Sandbox running at http://${SANDBOX_BIND}/command"
    ;;
  down)
    "$ENGINE" compose -f compose.sandbox.yml down
    ;;
  logs)
    "$ENGINE" compose -f compose.sandbox.yml logs -f
    ;;
  ps)
    "$ENGINE" compose -f compose.sandbox.yml ps
    ;;
  *)
    echo "Usage: $0 [up|down|logs|ps]"
    exit 2
    ;;
esac
