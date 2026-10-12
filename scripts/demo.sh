#!/usr/bin/env bash
# Make a synthetic "soundscape" and turn it into a postcard — no mic needed.
set -euo pipefail

OUT="${1:-/tmp/wanderear-demo.wav}"

if ! command -v ffmpeg >/dev/null; then
  echo "ffmpeg not found; install it or pass an existing audio file to: wanderear analyze <file>"
  exit 1
fi

ffmpeg -y -loglevel error \
  -f lavfi -i "sine=frequency=3200:duration=4" \
  -f lavfi -i "sine=frequency=180:duration=4" \
  -filter_complex "amix=inputs=2,tremolo=f=6:d=0.6" \
  -ar 16000 -ac 1 "$OUT"

echo "wrote $OUT"
wanderear analyze "$OUT" --narrator template