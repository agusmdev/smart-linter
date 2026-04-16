#!/usr/bin/env bash
# benchmark-real-repos.sh — Measure smart-linter findings on real FastAPI repos
#
# Outputs:
#   METRIC real_findings=N    — total violations found across benchmark repos
#   METRIC false_positives=N  — violations on known-clean code
#   METRIC score=N            — real_findings - (false_positives * 100)
#   METRIC total_rules=N      — number of active rules

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

REPO1="/tmp/fastapi-benchmark/backend"
REPO2="/tmp/fastapi-boiler/src"

# Ensure repos exist
if [ ! -d "$REPO1" ]; then
    echo "ERROR: $REPO1 not found. Clone the benchmark repos first." >&2
    exit 1
fi

rm -rf .smart_linter_cache/

# Count active rules
TOTAL_RULES=$(uv run python3 -c "
from smart_linter.registry import get_all_rules
rules = get_all_rules()
print(len(rules))
")

echo "Active rules: $TOTAL_RULES"
echo "METRIC total_rules=$TOTAL_RULES"

# --- Run on real repos ---
TOTAL_FINDINGS=0

for REPO in "$REPO1" "$REPO2"; do
    if [ ! -d "$REPO" ]; then
        echo "SKIP: $REPO not found"
        continue
    fi
    REPO_NAME=$(basename "$(dirname "$REPO")")
    echo ""
    echo "=== Linting $REPO_NAME ==="
    OUTPUT=$(uv run smart-linter check "$REPO" --no-cache --format json 2>/dev/null) || true
    COUNT=$(echo "$OUTPUT" | python3 -c "
import json, sys
data = sys.stdin.read().strip()
if not data:
    print(0)
else:
    try:
        objs = json.loads(data)
        if isinstance(objs, list):
            print(len(objs))
        else:
            print(1)
    except json.JSONDecodeError:
        print(0)
" 2>/dev/null || echo 0)

    # Show breakdown by rule
    echo "$OUTPUT" | python3 -c "
import json, sys
data = sys.stdin.read().strip()
if data:
    try:
        objs = json.loads(data)
        if isinstance(objs, list):
            from collections import Counter
            counts = Counter(o.get('code', 'unknown') for o in objs)
            for code, cnt in sorted(counts.items()):
                print(f'  {code}: {cnt}')
    except json.JSONDecodeError:
        pass
" 2>/dev/null || true

    echo "  Total: $COUNT violations"
    TOTAL_FINDINGS=$((TOTAL_FINDINGS + COUNT))
done

echo ""
echo "METRIC real_findings=$TOTAL_FINDINGS"

# --- False positive check ---
echo ""
echo "=== False positive check ==="
CLEAN_DIR=$(mktemp -d)
cat > "$CLEAN_DIR/clean_fastapi.py" << 'CLEAN_EOF'
"""Clean FastAPI code — should produce zero violations."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.models import Item, ItemCreate, ItemPublic
from app.schemas import Message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/", response_model=list[ItemPublic])
async def read_items(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Retrieve items."""
    items = await session.execute(
        Item.__table__.select().where(Item.owner_id == current_user.id)
    )
    return items.all()


@router.post("/", response_model=ItemPublic, status_code=201)
async def create_item(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    item_in: ItemCreate,
) -> Any:
    """Create new item."""
    item = Item(**item_in.model_dump(), owner_id=current_user.id)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}", response_model=Message)
async def delete_item(
    session: SessionDep,
    current_user: CurrentUser,
    item_id: int,
) -> Any:
    """Delete an item."""
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    if item.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    await session.delete(item)
    await session.commit()
    return Message(message="Item deleted successfully")


@router.get("/health")
def health_check() -> bool:
    """Health check endpoint."""
    return True
CLEAN_EOF

CLEAN_OUTPUT=$(uv run smart-linter check "$CLEAN_DIR/clean_fastapi.py" --no-cache --format json 2>/dev/null) || true
FALSE_POSITIVES=$(echo "$CLEAN_OUTPUT" | python3 -c "
import json, sys
data = sys.stdin.read().strip()
if not data:
    print(0)
else:
    try:
        objs = json.loads(data)
        if isinstance(objs, list):
            print(len(objs))
        else:
            print(1)
    except json.JSONDecodeError:
        print(0)
" 2>/dev/null || echo 0)
rm -rf "$CLEAN_DIR"

echo "  False positives: $FALSE_POSITIVES"
echo "METRIC false_positives=$FALSE_POSITIVES"

# --- Score ---
SCORE=$((TOTAL_FINDINGS - FALSE_POSITIVES * 100))
echo ""
echo "=== Summary ==="
echo "  real_findings:    $TOTAL_FINDINGS"
echo "  false_positives:  $FALSE_POSITIVES"
echo "  total_rules:      $TOTAL_RULES"
echo "  score:            $SCORE"
echo "METRIC score=$SCORE"
