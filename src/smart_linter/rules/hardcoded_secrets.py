"""SEC002: Detect potential hardcoded secrets, passwords, API keys, and tokens."""

from __future__ import annotations

import ast
import re
from typing import ClassVar

from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)

SECRET_PATTERNS: tuple[str, ...] = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "secret_key",
    "secret_key_base",
    "api_key",
    "apikey",
    "api_secret",
    "token",
    "access_token",
    "refresh_token",
    "auth_token",
    "bearer_token",
    "private_key",
    "public_key",
    "aws_secret",
    "aws_access_key",
    "database_url",
    "db_url",
    "connection_string",
    "encryption_key",
    "signing_key",
    "credentials",
    "credential",
)

_PLACEHOLDER_RE = re.compile(
    r"^("
    r"x{3,}"
    r"|changeme"
    r"|placeholder"
    r"|todo"
    r"|your_.*_here"
    r"|replace_me"
    r"|insert_.*"
    r"|redacted"
    r"|example"
    r"|sample"
    r"|test"
    r"|dummy"
    r"|fake"
    r"|mock"
    r"|default"
    r"|none"
    r"|null"
    r"|n/?a"
    r")$",
    re.IGNORECASE,
)

_MIN_SECRET_LENGTH = 4


def _is_secret_name(name: str) -> bool:
    lower = name.lower()
    return any(pattern in lower for pattern in SECRET_PATTERNS)


def _is_placeholder(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    if len(stripped) < _MIN_SECRET_LENGTH:
        return True
    return bool(_PLACEHOLDER_RE.match(stripped))


def _is_in_main_guard(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> bool:
    parent = parent_map.get(node)
    while parent is not None:
        if isinstance(parent, ast.If):
            test = parent.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == "__main__"
            ):
                return True
        parent = parent_map.get(parent)
    return False


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


class HardcodedSecretsRule(Rule):
    id: ClassVar[str] = "SEC002"
    description: ClassVar[str] = (
        "Potential hardcoded secret detected — use environment variables or a secrets manager"
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "vulnerability", "secrets")

    @classmethod
    def should_check(cls, source: str) -> bool:
        lower = source.lower()
        return any(p in lower for p in SECRET_PATTERNS)

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        parent_map = _build_parent_map(tree)
        violations: list[Violation] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue

            if not isinstance(node.value, ast.Constant) or not isinstance(
                node.value.value, str
            ):
                continue

            value: str = node.value.value

            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue

                name = target.id

                if name.startswith("_"):
                    continue

                if not _is_secret_name(name):
                    continue

                if _is_placeholder(value):
                    continue

                if _is_in_main_guard(node, parent_map):
                    continue

                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=(
                            f"Potential hardcoded secret in variable `{name}` — "
                            f"use environment variables or a secrets manager"
                        ),
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
                            title="Move secret to environment variable",
                            replacement=f'{name} = os.environ["{name.upper()}"]',
                            explanation=(
                                "Hardcoded secrets in source code are a security risk. "
                                "Use environment variables, a secrets manager, or a "
                                "configuration file outside version control."
                            ),
                        ),
                        filename=filename,
                    )
                )

        return violations
