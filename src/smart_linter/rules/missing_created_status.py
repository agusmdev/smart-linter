"""FAST002: Detect POST creation endpoints that don't set status_code=201.

POST endpoints that create resources should return HTTP 201 (Created) instead
of the default 200 (OK). This is a REST API convention documented in RFC 9110
and helps API consumers distinguish between creation and other operations.

Ruff cannot detect this because it requires understanding FastAPI's decorator
semantics and the relationship between POST and resource creation.
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

HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "options", "head"})

# Function name patterns that suggest resource creation
CREATE_PATTERNS = frozenset({
    "create",
    "add",
    "new",
    "insert",
    "save",
    "store",
    "write",
    "register",
    "signup",
    "submit",
    "post",
    "upload",
    "make",
})


def _get_qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


def _is_post_decorator(node: ast.expr) -> bool:
    """Check if the decorator is a @router.post(...) or @app.post(...)."""
    if isinstance(node, ast.Call):
        func = node.func
    elif isinstance(node, ast.Attribute):
        func = node
    else:
        return False

    if isinstance(func, ast.Attribute) and func.attr.lower() == "post":
        return True
    return False


def _has_status_code(decorator: ast.expr) -> bool:
    """Check if the decorator has status_code keyword with 201."""
    if not isinstance(decorator, ast.Call):
        return False
    for kw in decorator.keywords:
        if kw.arg == "status_code":
            if isinstance(kw.value, ast.Constant) and kw.value.value == 201:
                return True
            # status.HTTP_201_CREATED
            if isinstance(kw.value, ast.Attribute) and "201" in kw.value.attr:
                return True
            return True  # Any explicit status_code is intentional
    return False


def _suggests_creation(func_name: str) -> bool:
    """Check if the function name suggests resource creation."""
    lower = func_name.lower()
    # Check for create_, add_, new_ prefixes or _create, _add suffixes
    for pattern in CREATE_PATTERNS:
        if lower.startswith(pattern + "_") or lower.endswith("_" + pattern):
            return True
        if lower == pattern:
            return True
    return False


def _extract_path_from_decorator(decorator: ast.Call) -> str:
    """Extract URL path from decorator."""
    if decorator.args and isinstance(decorator.args[0], ast.Constant):
        if isinstance(decorator.args[0].value, str):
            return decorator.args[0].value
    return ""


class MissingCreatedStatusRule(Rule):
    id: ClassVar[str] = "FAST002"
    description: ClassVar[str] = (
        "POST endpoint that creates resources should return status_code=201 (Created)"
    )
    severity: ClassVar[Severity] = Severity.INFO
    tags: ClassVar[tuple[str, ...]] = ("api-quality", "fastapi", "rest")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return ".post(" in source or "@router.post" in source or "@app.post" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        func_nodes = []
        if node_index:
            func_nodes.extend(node_index.get(ast.FunctionDef, []))
            func_nodes.extend(node_index.get(ast.AsyncFunctionDef, []))
        if not func_nodes:
            func_nodes = [
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

        for func in func_nodes:
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Find a POST decorator
            post_dec = None
            for dec in func.decorator_list:
                if _is_post_decorator(dec):
                    post_dec = dec
                    break

            if post_dec is None:
                continue

            # Skip if has status_code
            if _has_status_code(post_dec):
                continue

            # Only flag if function name suggests creation
            if not _suggests_creation(func.name):
                continue

            path = ""
            if isinstance(post_dec, ast.Call):
                path = _extract_path_from_decorator(post_dec)

            path_desc = f" `{path}`" if path else ""
            message = (
                f"POST endpoint `{func.name}`{path_desc} creates a resource but "
                f"uses default status 200. Add `status_code=201` to the decorator "
                f"to follow REST conventions (RFC 9110)."
            )

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=message,
                    location=Location(
                        row=func.lineno,
                        column=func.col_offset,
                    ),
                    end_location=Location(
                        row=func.end_lineno or func.lineno,
                        column=func.end_col_offset or func.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title=f"Add `status_code=201` to `{func.name}`",
                        replacement=f'@router.post("{path}", status_code=201)',
                        explanation=(
                            "HTTP 201 (Created) is the standard response status for "
                            "resource creation endpoints. It tells API consumers that "
                            "a new resource was created, distinguishing it from a "
                            "general update or action endpoint."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
