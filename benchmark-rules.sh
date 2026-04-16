#!/usr/bin/env bash
# benchmark-rules.sh — Validate a new smart-linter rule.
# Usage: bash benchmark-rules.sh <RULE_ID>
# Example: bash benchmark-rules.sh SEC004

set -euo pipefail

RULE_ID="${1:?Usage: bash benchmark-rules.sh <RULE_ID>}"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
FIXTURE="$PROJECT_ROOT/tests/fixtures/fastapi_example.py"

rule_loads=0
tests_pass=0
violations_found=0
false_positives=0
full_suite_pass=0

echo "=== Benchmark for rule: $RULE_ID ==="

# --- 1. Check that the rule module loads ---
echo "[1/5] Checking rule loads..."
if uv run python -c "
import importlib.metadata
rules = importlib.metadata.entry_points(group='smart_linter.rules')
for ep in rules:
    loaded = ep.load()
    if getattr(loaded, 'id', None) == '$RULE_ID':
        print(f'  Found: {ep.name} -> {ep.value}')
        raise SystemExit(0)
raise SystemExit(1)
" 2>/dev/null; then
    rule_loads=1
    echo "  ✓ Rule loads successfully"
else
    echo "  ✗ Rule failed to load"
fi

echo "METRIC rule_loads=$rule_loads"

# --- 2. Run smart-linter with --select on the fixture ---
echo "[2/5] Running smart-linter --select $RULE_ID on fixture..."
output=$(uv run smart-linter check "$FIXTURE" --select "$RULE_ID" --format json 2>/dev/null || true)
# Count occurrences of the rule ID in JSON output
violations_found=$(echo "$output" | python3 -c "
import json, sys
data = sys.stdin.read().strip()
if not data:
    print(0)
else:
    try:
        objs = json.loads(data)
        if isinstance(objs, list):
            print(sum(1 for o in objs if o.get('code') == '$RULE_ID'))
        else:
            print(1 if objs.get('code') == '$RULE_ID' else 0)
    except json.JSONDecodeError:
        print(0)
" 2>/dev/null || echo 0)
echo "  Found $violations_found violation(s)"
echo "METRIC violations_found=$violations_found"

# --- 3. False positive check: run on a clean snippet ---
echo "[3/5] Checking for false positives..."
CLEAN_DIR=$(mktemp -d)
cat > "$CLEAN_DIR/clean.py" << 'CLEAN_EOF'
"""Clean code — should produce zero violations."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def fetch_data(url: str) -> dict:
    """A well-behaved async function."""
    await asyncio.sleep(0.1)
    return {"url": url, "status": "ok"}


def process_items(items: list[str]) -> list[str]:
    """Process items using a list comprehension."""
    return [item.strip().upper() for item in items if item]


class DataStore:
    """A class with proper instance attributes."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)
CLEAN_EOF

clean_output=$(uv run smart-linter check "$CLEAN_DIR/clean.py" --select "$RULE_ID" --format json 2>/dev/null || true)
false_positives=$(echo "$clean_output" | python3 -c "
import json, sys
data = sys.stdin.read().strip()
if not data:
    print(0)
else:
    try:
        objs = json.loads(data)
        if isinstance(objs, list):
            print(sum(1 for o in objs if o.get('code') == '$RULE_ID'))
        else:
            print(1 if objs.get('code') == '$RULE_ID' else 0)
    except json.JSONDecodeError:
        print(0)
" 2>/dev/null || echo 0)
rm -rf "$CLEAN_DIR"

if [ "$false_positives" -eq 0 ]; then
    echo "  ✓ No false positives"
else
    echo "  ✗ $false_positives false positive(s) on clean code"
fi

echo "METRIC false_positives=$false_positives"

# --- 4. Run rule-specific tests ---
echo "[4/5] Running rule-specific tests..."
rule_lower=$(echo "$RULE_ID" | tr '[:upper:]' '[:lower:]')
test_files=$(find "$PROJECT_ROOT/tests" -name "test_${rule_lower}_*" -type f -name '*.py' 2>/dev/null || true)

if [ -n "$test_files" ]; then
    if uv run pytest $test_files --tb=short 2>&1 > /tmp/benchmark_rule_tests.txt; then
        tests_pass=1
        echo "  ✓ Rule-specific tests pass"
    else
        echo "  ✗ Rule-specific tests failed"
    fi
    tail -5 /tmp/benchmark_rule_tests.txt
else
    echo "  ⚠ No test file found matching test_${rule_lower}_* (skipping)"
    tests_pass=1
fi

echo "METRIC tests_pass=$tests_pass"

# --- 5. Run full test suite ---
echo "[5/5] Running full test suite..."
if uv run pytest --tb=short -q 2>&1 > /tmp/benchmark_full_suite.txt; then
    full_suite_pass=1
    echo "  ✓ Full test suite passes"
else
    echo "  ✗ Full test suite has failures"
fi
tail -3 /tmp/benchmark_full_suite.txt

echo "METRIC full_suite_pass=$full_suite_pass"

# --- Summary ---
echo ""
echo "=== Summary ==="
echo "  rule_loads:       $rule_loads"
echo "  tests_pass:       $tests_pass"
echo "  violations_found: $violations_found"
echo "  false_positives:  $false_positives"
echo "  full_suite_pass:  $full_suite_pass"

# Exit 0 only if all critical checks pass
if [ "$rule_loads" -eq 1 ] && [ "$tests_pass" -eq 1 ] && [ "$false_positives" -eq 0 ] && [ "$full_suite_pass" -eq 1 ]; then
    echo "  ✓ All checks passed"
    exit 0
else
    echo "  ✗ Some checks failed"
    exit 1
fi
