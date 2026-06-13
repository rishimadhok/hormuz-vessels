#!/usr/bin/env bash
# One-command rerun of the full Strait of Hormuz pipeline on any bbox/date range.
#
#   ./run_all.sh "min_lon,min_lat,max_lon,max_lat" START_YYYY-MM-DD END_YYYY-MM-DD
#
# Defaults reproduce the chokepoint demo (Jan–Jun 2026). Runs:
#   detect (CFAR + land mask) -> temporal-persistence filter (islands/rigs)
#   -> coverage normalization -> news feed -> Opus analyst brief -> stage web.
#
# Requirements: ./.venv (Python 3.12, `pip install -e .`), and ANTHROPIC_API_KEY
# in .env for the brief step (everything else needs no credentials — Sentinel-1
# comes anonymously from Microsoft Planetary Computer).
set -euo pipefail

BBOX="${1:-56.0,26.2,56.9,26.9}"
START="${2:-2026-01-09}"
END="${3:-2026-06-11}"

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HERE/.venv/bin/python"
export PYTHONPATH="$HERE/src"

echo "[1/5] detect -> persistence -> counts -> oil   (bbox=$BBOX  $START..$END)"
"$PY" -m hormuz.cli run --no-verify --bbox "$BBOX" --start "$START" --end "$END" \
  --max-scenes 9999 --max-candidates 100000

echo "[2/5] coverage normalization"
"$PY" "$HERE/scripts/coverage.py"

echo "[3/5] news / OSINT feed"
"$PY" "$HERE/scripts/gen_news.py"

echo "[4/5] Opus 4.8 analyst brief (skipped if no ANTHROPIC_API_KEY)"
"$PY" -m hormuz.cli brief --bbox "$BBOX" --start "$START" --end "$END" \
  || echo "    brief skipped (set ANTHROPIC_API_KEY in .env to enable)"

echo "[5/5] stage web artifacts -> web/public"
"$PY" "$HERE/scripts/stage_web.py"

echo
echo "Done. Preview:  (cd web/public && python -m http.server 8765)  ->  http://localhost:8765"
echo "Deploy:         (cd web/public && vercel deploy --prod)"
echo
echo "NOTE: this runs all scenes in the range sequentially. For long ranges, the"
echo "parallel per-date approach (one 'hormuz run --artifacts-dir' per date, then"
echo "scripts/merge_runs.py) is much faster — see README."
