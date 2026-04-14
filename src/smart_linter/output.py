"""Output formatters: text, JSON (ruff-compatible), SARIF 2.1.0."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from smart_linter.models import Violation


def format_text(violations: list[Violation]) -> str:
    if not violations:
        return "No issues found."

    lines: list[str] = []
    for v in violations:
        fix_hint = ""
        if v.fix:
            fix_hint = f"\n  💡 {v.fix.title}"
            if v.fix.replacement:
                fix_hint += f"\n     Suggestion: {v.fix.replacement}"

        lines.append(
            f"{v.filename}:{v.location.row}:{v.location.column}: "
            f"{v.severity.value.upper()} {v.rule_id} "
            f"{v.message}{fix_hint}"
        )
    return "\n".join(lines)


def format_json(violations: list[Violation]) -> str:
    return json.dumps(
        [v.to_ruff_json() for v in violations],
        indent=2,
    )


def format_sarif(violations: list[Violation], tool_version: str = "0.1.0") -> str:
    rules_map: dict[str, dict] = {}
    for v in violations:
        if v.rule_id not in rules_map:
            rules_map[v.rule_id] = {
                "id": v.rule_id,
                "shortDescription": {"text": v.message.split(". ")[0]},
            }

    level_map = {"error": "error", "warning": "warning", "info": "note"}

    results = []
    for v in violations:
        results.append(
            {
                "ruleId": v.rule_id,
                "level": level_map.get(v.severity.value, "warning"),
                "message": {"text": v.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": v.filename},
                            "region": {
                                "startLine": v.location.row,
                                "startColumn": v.location.column,
                                **(
                                    {
                                        "endLine": v.end_location.row,
                                        "endColumn": v.end_location.column,
                                    }
                                    if v.end_location
                                    else {}
                                ),
                            },
                        }
                    }
                ],
                **(
                    {
                        "fixes": [
                            {
                                "description": {"text": v.fix.title},
                                "artifactChanges": [
                                    {
                                        "artifactLocation": {"uri": v.filename},
                                        "replacements": [
                                            {
                                                "deletedRegion": {
                                                    "startLine": v.location.row,
                                                    "startColumn": v.location.column,
                                                },
                                                "insertedContent": {
                                                    "text": v.fix.replacement or ""
                                                },
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                    if v.fix and v.fix.replacement
                    else {}
                ),
            }
        )

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "smart-linter",
                        "version": tool_version,
                        "rules": list(rules_map.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2)
