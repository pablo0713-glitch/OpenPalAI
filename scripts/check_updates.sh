#!/usr/bin/env bash
# Checks if the remote main branch has commits ahead of the local checkout.
# Designed to run as a systemd timer once per day.
# View results: journalctl -u openpalai-update-check -n 20

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR" || { echo "ERROR: Cannot cd to $REPO_DIR"; exit 1; }

git fetch --quiet origin main 2>/dev/null || {
    echo "WARNING: Could not reach GitHub. Check network connectivity."
    exit 0
}

BEHIND=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
CURRENT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
LATEST=$(git rev-parse --short origin/main 2>/dev/null || echo "unknown")

if [ "$BEHIND" -gt 0 ]; then
    echo "======================================"
    echo "  UPDATE AVAILABLE — $BEHIND new commit(s)"
    echo "======================================"
    echo "  Local:  $CURRENT"
    echo "  Remote: $LATEST"
    echo ""
    echo "  To update (Podman):"
    echo "    cd $REPO_DIR"
    echo "    git pull"
    echo "    podman compose build"
    echo "    podman compose up -d"
    echo ""
    echo "  To update (Docker):"
    echo "    cd $REPO_DIR"
    echo "    git pull"
    echo "    docker compose build"
    echo "    docker compose up -d"
    echo "======================================"

    # Optional: Discord webhook notification.
    # Set DISCORD_WEBHOOK_URL in your shell environment or uncomment and
    # hardcode it here. The URL is never committed — keep it out of the repo.
    #
    # DISCORD_WEBHOOK_URL=""
    # if [ -n "${DISCORD_WEBHOOK_URL:-}" ]; then
    #     curl -s -X POST "$DISCORD_WEBHOOK_URL" \
    #         -H "Content-Type: application/json" \
    #         -d "{\"content\": \"**OpenPalAI update available** — $BEHIND new commit(s) on \`main\` (current: \`$CURRENT\`, latest: \`$LATEST\`). Pull and rebuild when ready.\"}" \
    #         > /dev/null && echo "  Discord notification sent."
    # fi
else
    echo "OpenPalAI is up to date (commit: $CURRENT)."
fi
