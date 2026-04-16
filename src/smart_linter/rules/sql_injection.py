"""SEC001: Detect SQL injection via string formatting in query construction."""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)

SQL_KEYWORDS = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "EXECUTE",
        "FROM",
        "WHERE",
        "JOIN",
        "UNION",
        "SET",
    }
)

EXECUTE_METHODS = frozenset({"execute", "executemany"})

MIGRATION_PATH_PATTERNS = ("/revisions/", "/migrations/", "/alembic/")


def _extract_str_values(node: ast.expr) -> list[str]:
    """Extract all string literal values from an expression subtree."""
    values: list[str] = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        values.append(node.value)
    elif isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                values.append(part.value)
    elif isinstance(node, ast.BinOp):
        values.extend(_extract_str_values(node.left))
        values.extend(_extract_str_values(node.right))
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "format"
        and isinstance(node.func.value, ast.Constant)
        and isinstance(node.func.value.value, str)
    ):
        values.append(node.func.value.value)
    return values


def _contains_sql_keyword(node: ast.expr) -> bool:
    """Check if any string literal in the node contains an SQL keyword."""
    for value in _extract_str_values(node):
        upper = value.upper()
        for keyword in SQL_KEYWORDS:
            if keyword in upper:
                return True
    return False


def _is_formatted_string(arg: ast.expr) -> bool:
    """Check if the argument is a string built with formatting."""
    if isinstance(arg, ast.JoinedStr):
        return True

    if isinstance(arg, ast.BinOp):
        if isinstance(arg.op, ast.Mod):
            return True
        if isinstance(arg.op, ast.Add):
            return True

    return bool(isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format")


def _describe_format_type(arg: ast.expr) -> str:
    """Return a human-readable name for the formatting method used."""
    if isinstance(arg, ast.JoinedStr):
        return "f-string"
    if isinstance(arg, ast.BinOp):
        if isinstance(arg.op, ast.Mod):
            return "% formatting"
        if isinstance(arg.op, ast.Add):
            return "string concatenation (+)"
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "format":
        return ".format()"
    return "string formatting"


class SqlInjectionRule(Rule):
    id: ClassVar[str] = "SEC001"
    description: ClassVar[str] = (
        "SQL query constructed with string formatting — use parameterized queries to prevent SQL injection"
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "vulnerability", "injection")

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        if any(p in filename for p in MIGRATION_PATH_PATTERNS):
            return []

        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        call_nodes = node_index.get(ast.Call, []) if node_index else []
        if not call_nodes:
            call_nodes = (n for n in ast.walk(tree) if isinstance(n, ast.Call))

        for node in call_nodes:

            if not isinstance(node.func, ast.Attribute):
                continue

            if node.func.attr not in EXECUTE_METHODS:
                continue

            if not node.args:
                continue

            # Skip if second argument exists — likely parameterized
            if len(node.args) >= 2 and node.func.attr == "execute":
                continue

            first_arg = node.args[0]

            if not _is_formatted_string(first_arg):
                continue

            if not _contains_sql_keyword(first_arg):
                continue

            fmt_type = _describe_format_type(first_arg)
            message = (
                f"SQL query constructed with {fmt_type} in `{node.func.attr}()` — "
                f"use parameterized queries to prevent SQL injection"
            )

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=message,
                    location=Location(
                        row=node.lineno,
                        column=node.col_offset,
                    ),
                    end_location=Location(
                        row=node.end_lineno or node.lineno,
                        column=node.end_col_offset or node.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title="Use parameterized query instead of string formatting",
                        replacement=("cursor.execute('SELECT ... WHERE id = %s', (user_id,))"),
                        explanation=(
                            "String formatting in SQL queries allows injection attacks. "
                            "Use parameterized queries with placeholders (%s, ?, :name)."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
