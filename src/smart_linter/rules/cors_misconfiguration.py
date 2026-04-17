"""SEC007: Detect CORS misconfiguration: allow_origins=["*"] with allow_credentials=True.

This combination is actually rejected by the CORS specification (browsers will
not send credentials when the origin is wildcard). It usually indicates the
developer misunderstood CORS and should specify explicit origins instead.

Ruff cannot detect this because it requires understanding middleware configuration
semantics.
"""

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


def _get_qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


def _is_add_middleware_call(node: ast.Call) -> bool:
    """Check if this is app.add_middleware(CORSMiddleware, ...)."""
    if not node.args:
        return False
    first_arg = node.args[0]
    name = _get_qualified_name(first_arg)
    return name in ("CORSMiddleware", "cors.CORSMiddleware", "starlette.middleware.cors.CORSMiddleware")


def _extract_allow_origins(node: ast.Call) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == "allow_origins":
            return kw.value
    return None


def _extract_allow_credentials(node: ast.Call) -> ast.expr | None:
    for kw in node.keywords:
        if kw.arg == "allow_credentials":
            return kw.value
    return None


def _is_wildcard_origins(node: ast.expr) -> bool:
    """Check if allow_origins is ["*"]."""
    if isinstance(node, ast.List) and len(node.elts) == 1:
        elt = node.elts[0]
        if isinstance(elt, ast.Constant) and elt.value == "*":
            return True
    return False


def _is_truthy(node: ast.expr) -> bool:
    """Check if an expression evaluates to True."""
    if isinstance(node, ast.Constant):
        return node.value is True
    if isinstance(node, ast.NameConstant):  # Python 3.7
        return node.value is True  # type: ignore
    return False


class CorsMisconfigurationRule(Rule):
    id: ClassVar[str] = "SEC007"
    description: ClassVar[str] = (
        "CORS misconfiguration: allow_origins=[\"*\"] with allow_credentials=True "
        "is rejected by browsers"
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "cors", "misconfiguration")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "CORSMiddleware" in source and "allow_origins" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        call_nodes = node_index.get(ast.Call, []) if node_index else []
        if not call_nodes:
            call_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

        for node in call_nodes:
            if not isinstance(node, ast.Call):
                continue

            if not _is_add_middleware_call(node):
                continue

            origins = _extract_allow_origins(node)
            credentials = _extract_allow_credentials(node)

            if origins is None or credentials is None:
                continue

            if not _is_wildcard_origins(origins):
                continue

            if not _is_truthy(credentials):
                continue

            message = (
                "CORS misconfiguration: `allow_origins=[\"*\"]` with "
                "`allow_credentials=True` is rejected by browsers per the CORS spec. "
                "Specify explicit origins instead."
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
                        title="Replace wildcard origins with explicit list",
                        replacement=(
                            'app.add_middleware(\n'
                            '    CORSMiddleware,\n'
                            '    allow_origins=["https://example.com", "http://localhost:3000"],\n'
                            '    allow_credentials=True,\n'
                            '    allow_methods=["*"],\n'
                            '    allow_headers=["*"],\n'
                            ')'
                        ),
                        explanation=(
                            "Per the CORS specification (Fetch Standard), browsers reject "
                            "responses with `Access-Control-Allow-Origin: *` when credentials "
                            "are included. Use an explicit list of allowed origins, or set "
                            "`allow_credentials=False` if you truly need wildcard origins."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
