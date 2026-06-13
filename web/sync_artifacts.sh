#!/usr/bin/env bash
# Copy pipeline artifacts into web/public/ so the static site can fetch() them.
# Run this from anywhere; paths are resolved relative to this script.
#
#   ./web/sync_artifacts.sh
#
# Source (repo root, one level up from web/):
#   ../artifacts/{detections.json,timeseries.json,brief.md,chips/}
#   ../data/timeline.json
# Destination:
#   web/public/artifacts/...
#   web/public/data/timeline.json
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC_ART="$ROOT/artifacts"
SRC_DATA="$ROOT/data"
DEST="$HERE/public"

mkdir -p "$DEST/artifacts/chips" "$DEST/data"

# JSON + markdown (skip silently if a file doesn't exist yet)
for f in detections.json timeseries.json brief.md; do
  if [ -f "$SRC_ART/$f" ]; then
    cp "$SRC_ART/$f" "$DEST/artifacts/$f"
    echo "synced artifacts/$f"
  else
    echo "skip artifacts/$f (not present)"
  fi
done

# chips/ (overlays + per-candidate). rsync if available, else cp.
if [ -d "$SRC_ART/chips" ]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$SRC_ART/chips/" "$DEST/artifacts/chips/"
  else
    rm -rf "$DEST/artifacts/chips" && mkdir -p "$DEST/artifacts/chips"
    cp -R "$SRC_ART/chips/." "$DEST/artifacts/chips/"
  fi
  echo "synced artifacts/chips ($(ls "$DEST/artifacts/chips" | wc -l | tr -d ' ') files)"
else
  echo "skip artifacts/chips (not present)"
fi

# timeline
if [ -f "$SRC_DATA/timeline.json" ]; then
  cp "$SRC_DATA/timeline.json" "$DEST/data/timeline.json"
  echo "synced data/timeline.json"
else
  echo "skip data/timeline.json (not present)"
fi

echo "done -> $DEST"
