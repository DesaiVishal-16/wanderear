#!/usr/bin/env bash
# Expose the local WanderEar gallery on a public HTTPS URL — no account, no card.
#
# The gallery keeps running on your machine (that's the local-first philosophy);
# this just gives it a shareable URL so `wanderear sync` can reach it from your
# phone or a friend's laptop.
#
# Usage:
#   scripts/tunnel.sh [port]        # default port: 8000
#
# Uses cloudflared when installed (stable, fast). Falls back to a free
# localhost.run SSH tunnel, which needs nothing but ssh.
set -euo pipefail

PORT="${1:-8000}"
TARGET="http://localhost:${PORT}"

echo "Assuming the gallery is running at ${TARGET}"
echo "Start it with:  python web/server.py   (or: make serve)"
echo

if command -v cloudflared >/dev/null 2>&1; then
  echo "Opening a Cloudflare quick tunnel… (Ctrl-C to close)"
  exec cloudflared tunnel --url "${TARGET}"
fi

cat <<'EOF'
cloudflared not found — using a free localhost.run SSH tunnel instead.
For a more stable tunnel, install cloudflared:
  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

Opening tunnel… (Ctrl-C to close)
EOF
exec ssh -o StrictHostKeyChecking=accept-new -R "80:localhost:${PORT}" nokey@localhost.run
