"""RESP001: Detect FastAPI endpoints missing response_model.

FastAPI's `response_model` parameter enables response serialization, validation,
field filtering (e.g. stripping passwords), and automatic OpenAPI documentation.
Endpoints that return data without `response_model` risk leaking sensitive fields
and have incomplete API documentation. Ruff cannot detect this because it requires
understanding FastAPI's decorator semantics.
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

# Return type annotations that indicate a simple/primitive response (no response_model needed)
PRIMITIVE_RETURN_TYPES = frozenset({
    "bool", "int", "float", "str", "bytes", "None", "dict", "list",
    "Any", "JSONResponse", "HTMLResponse", "PlainTextResponse",
    "RedirectResponse", "StreamingResponse", "FileResponse",
    "Response", "starlette.responses.JSONResponse",
    "starlette.responses.HTMLResponse", "starlette.responses.Response",
})

# URL path patterns where response_model is typically not needed
SKIP_PATH_PATTERNS = frozenset({
    "health",
    "ping",
    "readiness",
    "liveness",
    "health-check",
})


def _get_qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


def _extract_path_from_decorator(decorator: ast.Call) -> str:
    """Extract URL path from decorator like @router.get('/items')."""
    if decorator.args and isinstance(decorator.args[0], ast.Constant):
        if isinstance(decorator.args[0].value, str):
            return decorator.args[0].value
    return ""


def _has_response_model(decorator: ast.Call) -> bool:
    """Check if the decorator has a response_model keyword argument."""
    for kw in decorator.keywords:
        if kw.arg == "response_model":
            return True
        if kw.arg == "response_class":
            return True
    return False


def _has_response_model_in_return_type(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool | None:
    """Check return type annotation.

    Returns:
        True if return type is a known primitive/response (no response_model needed)
        False if return type is complex (response_model recommended)
        None if no return type annotation
    """
    ret = func.returns
    if ret is None:
        return None

    # Check for subscripted generics: dict[str, str], list[int], etc.
    if isinstance(ret, ast.Subscript):
        base = _get_qualified_name(ret.value)
        if base in ("dict", "Dict", "list", "List", "set", "Set", "frozenset", "FrozenSet"):
            return True

    type_name = _get_qualified_name(ret)
    if type_name:
        if type_name in PRIMITIVE_RETURN_TYPES:
            return True
        return False

    # Union types like dict | None
    if isinstance(ret, ast.BinOp):
        return True

    return None


def _is_endpoint_decorator(node: ast.expr) -> str | None:
    """Return HTTP method if the node is an endpoint decorator, else None."""
    if isinstance(node, ast.Call):
        func = node.func
    elif isinstance(node, ast.Attribute):
        func = node
    else:
        return None

    if isinstance(func, ast.Attribute) and func.attr.lower() in HTTP_METHODS:
        return func.attr.lower()
    return None


def _is_health_endpoint(path: str) -> bool:
    """Check if the path looks like a health check endpoint."""
    path_lower = path.lower().strip("/")
    return path_lower in SKIP_PATH_PATTERNS or any(
        p in path_lower for p in ("/health", "/ping", "/readiness", "/liveness")
    )


class MissingResponseModelRule(Rule):
    id: ClassVar[str] = "RESP001"
    description: ClassVar[str] = (
        "API endpoint is missing `response_model` — response is not validated or documented"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("api-quality", "fastapi", "best-practice")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return any(
            f"@{prefix}.{method}" in source
            for prefix in ("router", "app", "api_router", "api")
            for method in HTTP_METHODS
        )

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

            # Find the endpoint decorator
            endpoint_dec = None
            method = None
            for dec in func.decorator_list:
                m = _is_endpoint_decorator(dec)
                if m:
                    endpoint_dec = dec
                    method = m
                    break

            if endpoint_dec is None or method is None:
                continue

            # Only check Call decorators (with parameters)
            if not isinstance(endpoint_dec, ast.Call):
                continue

            # Skip if has response_model
            if _has_response_model(endpoint_dec):
                continue

            # Extract path
            path = _extract_path_from_decorator(endpoint_dec)

            # Skip health check endpoints
            if _is_health_endpoint(path):
                continue

            # Skip if return type is clearly primitive
            ret_type_status = _has_response_model_in_return_type(func)
            if ret_type_status is True:
                continue

            method_upper = method.upper()
            path_desc = f" `{path}`" if path else ""

            if ret_type_status is None:
                message = (
                    f"Endpoint `{func.name}` ({method_upper}{path_desc}) has no "
                    f"`response_model` and no return type annotation. "
                    f"Add `response_model=YourSchema` for response validation and OpenAPI docs."
                )
            else:
                message = (
                    f"Endpoint `{func.name}` ({method_upper}{path_desc}) has no "
                    f"`response_model`. The return type `{ast.dump(func.returns)}` "
                    f"should be declared as `response_model` for proper serialization "
                    f"and field filtering."
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
                        title=f"Add `response_model` to `{func.name}`",
                        replacement=f"@router.{method}(\"{path}\", response_model=YourSchema)",
                        explanation=(
                            "Without `response_model`, FastAPI cannot: (1) validate the response, "
                            "(2) filter sensitive fields from ORM models, (3) generate accurate "
                            "OpenAPI documentation. Define a Pydantic model and add it as "
                            "`response_model=YourSchema`."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
