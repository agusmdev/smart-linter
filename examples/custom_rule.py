"""Example custom rule: detect print() statements in production code.

To use this rule, add to your pyproject.toml:

    [tool.smart-linter]
    custom-rules = ["examples.custom_rule:NoPrintInFunctionsRule"]

Or register via entry_points in your own package's pyproject.toml:

    [project.entry-points."smart_linter.rules"]
    no_print = "examples.custom_rule:NoPrintInFunctionsRule"
"""

import ast
from typing import ClassVar

from smart_linter.models import FixSuggestion, Location, Rule, Severity, Violation


class NoPrintInFunctionsRule(Rule):
    id: ClassVar[str] = "PRINT001"
    description: ClassVar[str] = (
        "print() statement found in function — use logging instead"
    )
    severity: ClassVar[Severity] = Severity.INFO
    tags: ClassVar[tuple[str, ...]] = ("style", "logging")

    def check(self, tree, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                if isinstance(child.func, ast.Name) and child.func.id == "print":
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"print() call in function `{node.name}` — use logging instead",
                            location=Location(
                                row=child.lineno, column=child.col_offset + 1
                            ),
                            severity=self.severity,
                            fix=FixSuggestion(
                                title="Replace print() with logging.info()",
                                replacement="logging.info(...)",
                                explanation="Use the logging module for structured, configurable output.",
                            ),
                            filename=filename,
                        )
                    )

        return violations
