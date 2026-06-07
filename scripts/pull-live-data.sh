#!/usr/bin/env bash
set -euo pipefail

REMOTE="${REMOTE:-}"
REMOTE_PATH="${REMOTE_PATH:-}"
TARGET="${TARGET:-./.sandbox/linux}"
INCLUDE_ENV="${INCLUDE_ENV:-0}"
INCLUDE_CHROMA="${INCLUDE_CHROMA:-0}"

if [ -z "$REMOTE" ] || [ -z "$REMOTE_PATH" ]; then
  cat >&2 <<'EOF'
Usage:
  REMOTE=user@host REMOTE_PATH=/srv/openpalai ./scripts/pull-live-data.sh

Optional:
  TARGET=./.sandbox/linux      Destination sandbox root
  INCLUDE_ENV=1                Also copy remote .env
  INCLUDE_CHROMA=1             Also copy ChromaDB vectors/cache instead of rebuilding locally
EOF
  exit 2
fi

mkdir -p "$TARGET"

excludes=()
if [ "$INCLUDE_CHROMA" != "1" ]; then
  excludes+=(--exclude 'memory/chroma/' --exclude '.cache/')
fi

rsync -az --delete "${excludes[@]}" "$REMOTE:$REMOTE_PATH/data/" "$TARGET/data/"

if [ "$INCLUDE_ENV" = "1" ]; then
  rsync -az "$REMOTE:$REMOTE_PATH/.env" "$TARGET/.env"
elif [ ! -f "$TARGET/.env" ]; then
  cat > "$TARGET/.env" <<'EOF'
# Sandbox configuration. Fill this through /setup or copy live env intentionally.
MODEL_PROVIDER=anthropic
SL_BRIDGE_HOST=0.0.0.0
SL_BRIDGE_PORT=8080
EOF
fi

echo "Pulled live data into $TARGET"
echo "Chroma/cache copied: $INCLUDE_CHROMA"
echo ".env copied: $INCLUDE_ENV"
