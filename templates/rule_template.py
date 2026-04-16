"""CATEGORY###: One-line description of what this rule detects."""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.ast_utils import build_parent_map, get_qualified_name  # add helpers as needed
from smart_linter.models import FixSuggestion, Location, Rule, Severity, Violation


class MyRule(Rule):
    """One-line description repeated here for docstring."""

    id: ClassVar[str] = "CATEGORY###"  # e.g. SEC004, PERF003, LOGIC002
    description: ClassVar[str] = "One-line description of what this rule detects"
    severity: ClassVar[Severity] = Severity.WARNING  # ERROR | WARNING | INFO
    tags: ClassVar[tuple[str, ...]] = ("category",)

    @classmethod
    def should_check(cls, source: str) -> bool:
        """Return True only if the source might contain the pattern.
        Use a cheap string check to skip files that definitely don't match."""
        return "keyword_or_symbol" in source  # customize this

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []
        # Option A: simple walk (use for straightforward patterns)
        for node in ast.walk(tree):
            if not isinstance(node, ast.YourNode):
                continue
            if not self._matches(node):
                continue
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=f"Describe the issue at line {node.lineno}",
                    location=Location(row=node.lineno, column=node.col_offset),
                    end_location=Location(
                        row=node.end_lineno or node.lineno,
                        column=node.end_col_offset or node.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title="Short title for the fix",
                        replacement="replacement code",
                        explanation="Why this fix works.",
                    ),
                    filename=filename,
                )
            )
        return violations

    def _matches(self, node: ast.AST) -> bool:
        return False  # replace with your detection logic
