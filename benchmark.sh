#!/usr/bin/env bash
# benchmark.sh — Measures smart-linter speed for pi-autoresearch optimization loop
#
# Usage: bash benchmark.sh [target]
#   target: "full" (default) - lints src/ + tests/ (~2.4s baseline)
#           "fixture"         - lints tests/fixtures/ only (~1.0s baseline)
#           "self"            - lints src/ only (the linter's own code)
#
# Output: METRIC lines parsed by pi-autoresearch
#   METRIC total_ms=X.XXX     — total wall-clock time in milliseconds
#   METRIC violations=N       — number of violations detected (safety check)

set -euo pipefail

TARGET="${1:-full}"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

case "$TARGET" in
  full)    PATHS="src/ tests/" ;;
  fixture) PATHS="tests/fixtures/" ;;
  self)    PATHS="src/" ;;
  *)       echo "Unknown target: $TARGET. Use: full, fixture, self" >&2; exit 1 ;;
esac

rm -rf .smart_linter_cache/

# Warm up import cache (first run is slower due to module loading)
uv run smart-linter check $PATHS --no-cache > /dev/null 2>&1 || true

START_NS=$(uv run python3 -c "import time; print(time.perf_counter_ns())")
JSON_OUTPUT=$(uv run smart-linter check $PATHS --no-cache --format json 2>/dev/null) || true
END_NS=$(uv run python3 -c "import time; print(time.perf_counter_ns())")

ELAPSED_NS=$((END_NS - START_NS))
ELAPSED_MS=$(uv run python3 -c "print(f'{$ELAPSED_NS / 1_000_000:.3f}')")

VIOLATION_COUNT=$(echo "$JSON_OUTPUT" | uv run python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data))" 2>/dev/null || echo "0")

echo "METRIC total_ms=$ELAPSED_MS"
echo "METRIC violations=$VIOLATION_COUNT"
