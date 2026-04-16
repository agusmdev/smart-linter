"""PRINT002: Detects print() calls in async functions (blocking I/O in async context)."""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.ast_utils import build_parent_map, is_in_context
from smart_linter.models import FixSuggestion, Location, Rule, Severity, Violation


class PrintInAsyncRule(Rule):
    """PRINT002: Flags print() calls inside async functions."""

    id: ClassVar[str] = "PRINT002"
    description: ClassVar[str] = "print() call in async function — use logging instead"
    severity: ClassVar[Severity] = Severity.INFO
    tags: ClassVar[tuple[str, ...]] = ("style", "async")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "async def" in source and "print(" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []
        parent_map = build_parent_map(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "print":
                continue
            if is_in_context(node, parent_map, ast.AsyncFunctionDef):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="print() call in async function — use logging instead",
                        location=Location(row=node.lineno, column=node.col_offset),
                        end_location=Location(
                            row=node.end_lineno or node.lineno,
                            column=node.end_col_offset or node.col_offset,
                        ),
                        severity=self.severity,
                        fix=FixSuggestion(
                            title="Replace print() with logger.info()",
                            replacement="logger.info(...)",
                            explanation="print() is blocking I/O and should not be used in async functions.",
                        ),
                        filename=filename,
                    )
                )
        return violations
