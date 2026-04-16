"""MCP server for smart-linter — enables AI agents to invoke linting directly."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "smart-linter MCP server requires the 'mcp' package. Install with: pip install smart-linter[mcp]",
        file=sys.stderr,
    )
    sys.exit(1)

from smart_linter.config import Config
from smart_linter.engine import run
from smart_linter.output import format_json, format_text
from smart_linter.registry import get_all_rules

mcp = FastMCP("smart-linter")


@mcp.tool()
def check_files(
    paths: list[str],
    select: list[str] | None = None,
    ignore: list[str] | None = None,
    output_format: str = "json",
) -> str:
    """Lint Python files for heuristic code quality issues.

    Detects issues that ruff cannot catch: sync calls in async endpoints,
    silent exception swallowing, hardcoded secrets, SQL injection patterns,
    resource leaks, performance anti-patterns, and more.

    Args:
        paths: List of file or directory paths to check
        select: List of rule IDs to enable (default: all rules)
        ignore: List of rule IDs to ignore
        output_format: Output format - "json" (structured),
            "text" (human-readable), or "fixes" (AI-parseable)

    Returns:
        Linting results with violations and fix suggestions
    """
    config = Config()
    if select:
        config.select = select
    if ignore:
        config.ignore = ignore

    target_paths = [Path(p) for p in paths]
    violations = run(target_paths, config)

    if output_format == "fixes":
        fixes = []
        for v in violations:
            entry = {
                "file": v.filename,
                "line": v.location.row,
                "column": v.location.column,
                "rule": v.rule_id,
                "severity": v.severity.value,
                "message": v.message,
            }
            if v.fix:
                entry["fix_title"] = v.fix.title
                if v.fix.replacement is not None:
                    entry["fix_replacement"] = v.fix.replacement
                if v.fix.explanation is not None:
                    entry["fix_explanation"] = v.fix.explanation
            fixes.append(entry)
        return json.dumps(fixes, indent=2)

    if output_format == "text":
        return format_text(violations)

    return format_json(violations)


@mcp.tool()
def list_rules() -> str:
    """List all available smart-linter rules with descriptions.

    Returns:
        JSON array of available rules with id, description, and severity
    """
    rules = get_all_rules()
    result = []
    for rule_id, rule_cls in sorted(rules.items()):
        result.append(
            {
                "id": rule_id,
                "description": rule_cls.description,
                "severity": rule_cls.severity.value,
                "tags": list(rule_cls.tags),
            }
        )
    return json.dumps(result, indent=2)


@mcp.tool()
def explain_rule(rule_id: str) -> str:
    """Get detailed explanation of a specific rule including what it detects and how to fix.

    Args:
        rule_id: The rule ID to explain (e.g. "ASYNC001")

    Returns:
        Detailed rule explanation with detection patterns and fix suggestions
    """
    rules = get_all_rules()
    if rule_id not in rules:
        return json.dumps({"error": f"Unknown rule: {rule_id}"})

    cls = rules[rule_id]
    result = {
        "id": rule_id,
        "description": cls.description,
        "severity": cls.severity.value,
        "tags": list(cls.tags),
    }

    if rule_id == "ASYNC001":
        from smart_linter.rules.async_sync import (
            BLOCKING_CALLS,
            PATHLIB_BLOCKING_METHODS,
        )

        patterns = []
        for call_name, (replacement, example) in BLOCKING_CALLS.items():
            patterns.append(f"`{call_name}()` → Use `{replacement}`: `{example}`")

        pathlib_methods = ", ".join(f"`.{m}()`" for m in sorted(PATHLIB_BLOCKING_METHODS))

        result.update(
            {
                "title": "Sync blocking call in async FastAPI endpoint",
                "safe_wrappers": [
                    "asyncio.to_thread(func, ...)",
                    "run_in_threadpool(func, ...)",
                    "loop.run_in_executor(None, func, ...)",
                    "anyio.to_thread.run_sync(func, ...)",
                ],
                "detection_patterns": patterns,
                "pathlib_methods": f"Also detects pathlib methods: {pathlib_methods}",
                "false_positive_prevention": (
                    "Does NOT flag: sync def endpoints, "
                    "non-decorated async functions, calls wrapped in safe "
                    "wrappers (asyncio.to_thread, run_in_threadpool), "
                    "awaited calls."
                ),
            }
        )

    return json.dumps(result, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
