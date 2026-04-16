---
name: optimize-speed
description: "Optimize smart-linter linting speed without breaking rule detection or tests"
---

## Metric

- **total_ms**: Wall-clock time to lint the full codebase (lower is better)
- **violations**: Number of violations detected — MUST stay at 16 (full) or 10 (fixture)
- Benchmark: `bash benchmark.sh full`

## Baseline

- total_ms ≈ 2400ms (full: src/ + tests/)
- violations = 16

## Validation (after EVERY change)

1. `bash benchmark.sh full` — measure speed, must print METRIC lines
2. `uv run pytest tests/ -x` — all tests must pass, zero failures
3. Violations count must remain 16 — fewer means a rule broke

## Scope

### CAN modify
- `src/smart_linter/engine.py` — file discovery, caching, parallel dispatch, lint pipeline
- `src/smart_linter/ast_utils.py` — AST analysis helpers, parent_map, func_index
- `src/smart_linter/registry.py` — rule discovery and loading
- `src/smart_linter/models.py` — data models (Violation, Location, etc.)
- `src/smart_linter/output.py` — output formatting
- `src/smart_linter/cli.py` — CLI entry point

### MUST NOT modify
- `tests/` — these are the validation suite, touching them invalidates the benchmark
- `src/smart_linter/rules/*.py` — rule logic must stay correct, speed gains come from engine/infrastructure
- `pyproject.toml` — no dependency changes
- `benchmark.sh` — the measurement tool itself

## Ideas to try (ordered by estimated impact)

1. **Cache parsed AST trees**: Parse once per file, share across all rules (currently each rule walks independently)
2. **Single-pass AST walk**: Walk the tree once, dispatch to all rule checkers instead of N walks
3. **Lazy rule loading**: Only import rule modules when `should_check()` passes for that file
4. **Content-hash cache key**: Use file content hash instead of mtime_ns — avoids cache misses from touch/rebuild
5. **Rule-level early exit in batch**: If all rules' `should_check()` fail for a file, skip it entirely
6. **Optimize parent_map construction**: Use iterative stack instead of recursive `ast.walk()` with parent tracking
7. **Reduce serialization overhead**: Avoid dict round-trips in ProcessPoolExecutor — use pickle protocol directly
8. **Skip .gitignored files earlier**: Apply gitignore patterns before file read, not after
9. **Parallel rule execution within single file**: Run independent rules concurrently on same AST
10. **Memory-efficient violation collection**: Use generators instead of building full lists in each rule

## Rules

- LOOP FOREVER. Never ask "should I continue?"
- total_ms is king. Lower = keep. Higher/equal = discard.
- If tests fail, DISCARD immediately.
- If violations count drops, DISCARD (a rule broke).
- Maximum 50 lines changed per iteration.
- Simpler code for equal speed = keep (removing code is always good).
- Every iteration MUST run the full validation suite before logging.
