"""ERR002: Detect raise inside except that loses original exception context.

When catching an exception and raising a new one, Python best practice (PEP 3134)
recommends using `raise NewError(...) from e` to preserve the original traceback.
Without this, debugging becomes much harder because the original error context is lost.

This is subtly different from ruff's B904 (which only checks bare raise inside except).
ERR002 detects the common pattern of raising a *new* exception without chaining,
which B904 intentionally does NOT flag.
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

# Exception types where re-raising without `from` is acceptable
_ACCEPTABLE_RE_RAISES = frozenset({
    "HTTPException",  # FastAPI/Starlette convention
    "NotImplementedError",
    "AssertionError",
})

# Known exception variable names in except handlers
_COMMON_EXCEPT_NAMES = frozenset({
    "e", "exc", "err", "ex", "error", "exception", "exc_info",
})


def _is_in_except_handler(
    node: ast.AST,
    parent_map: dict[ast.AST, ast.AST],
) -> ast.ExceptHandler | None:
    """Walk up to find if the node is inside an except handler body."""
    parent = parent_map.get(node)
    while parent is not None:
        if isinstance(parent, ast.ExceptHandler):
            return parent
        # Don't cross function boundaries
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return None
        parent = parent_map.get(parent)
    return None


def _has_explicit_chaining(raise_node: ast.Raise) -> bool:
    """Check if the raise has explicit exception chaining (from clause)."""
    return raise_node.cause is not None


def _get_caught_exception_name(handler: ast.ExceptHandler) -> str | None:
    """Get the variable name from `except SomeError as <name>`."""
    return handler.name


def _is_reraise_same_exception(
    raise_node: ast.Raise,
    caught_name: str | None,
) -> bool:
    """Check if the raise is re-raising the caught exception directly."""
    if raise_node.exc is None:
        return True  # bare `raise` always re-raises
    if isinstance(raise_node.exc, ast.Name) and caught_name:
        return raise_node.exc.id == caught_name
    return False


def _is_raise_from_wrapped_exception(
    raise_node: ast.Raise,
    caught_name: str | None,
) -> bool:
    """Check if the raised exception includes the caught exception as argument."""
    if caught_name is None or raise_node.exc is None:
        return False
    if isinstance(raise_node.exc, ast.Call):
        for arg in raise_node.exc.args:
            if isinstance(arg, ast.Name) and arg.id == caught_name:
                return True
            # str(e), repr(e) are acceptable
            if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                if arg.func.id in ("str", "repr") and arg.args:
                    inner = arg.args[0]
                    if isinstance(inner, ast.Name) and inner.id == caught_name:
                        return True
            # Check f-strings that include the caught exception
            if isinstance(arg, ast.JoinedStr):
                for part in arg.values:
                    if isinstance(part, ast.FormattedValue):
                        if isinstance(part.value, ast.Name) and part.value.id == caught_name:
                            return True
    return False


class LostExceptionContextRule(Rule):
    id: ClassVar[str] = "ERR002"
    description: ClassVar[str] = (
        "Exception raised inside except block without `from` — original context is lost"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("error-handling", "debugging", "best-practice")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "except" in source and "raise" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        parent_map = getattr(self, "_parent_map", None)
        if parent_map is None:
            from smart_linter.ast_utils import build_parent_map
            parent_map = build_parent_map(tree)

        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        raise_nodes: list[ast.AST] = []
        if node_index:
            # Collect Raise nodes by walking the indexed nodes
            for func_nodes in [node_index.get(ast.FunctionDef, []), node_index.get(ast.AsyncFunctionDef, [])]:
                for func in func_nodes:
                    for child in ast.walk(func):
                        if isinstance(child, ast.Raise):
                            raise_nodes.append(child)
        if not raise_nodes:
            raise_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]

        seen: set[tuple[str, int]] = set()

        for raise_node in raise_nodes:
            if not isinstance(raise_node, ast.Raise):
                continue

            # Skip if already has explicit chaining
            if _has_explicit_chaining(raise_node):
                continue

            # Skip bare raises (re-raise)
            if raise_node.exc is None:
                continue

            # Check if inside an except handler
            handler = _is_in_except_handler(raise_node, parent_map)
            if handler is None:
                continue

            caught_name = _get_caught_exception_name(handler)

            # Skip if re-raising same exception
            if _is_reraise_same_exception(raise_node, caught_name):
                continue

            # Skip if the caught exception is passed as argument
            if _is_raise_from_wrapped_exception(raise_node, caught_name):
                continue

            # Skip HTTPException and other acceptable re-raises in web contexts
            if isinstance(raise_node.exc, ast.Call):
                func = raise_node.exc.func
                exc_name = None
                if isinstance(func, ast.Name):
                    exc_name = func.id
                elif isinstance(func, ast.Attribute):
                    exc_name = func.attr
                if exc_name in _ACCEPTABLE_RE_RAISES:
                    continue

            key = (filename, raise_node.lineno)
            if key in seen:
                continue
            seen.add(key)

            # Build message
            caught_desc = f"`{caught_name}`" if caught_name else "an exception"
            exc_desc = self._describe_raised(raise_node.exc)
            message = (
                f"Raising {exc_desc} inside `except` block without `from` — "
                f"original exception ({caught_desc}) context is lost. "
                f"Use `raise ... from {caught_name or 'e'}` to preserve the traceback."
            )

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=message,
                    location=Location(
                        row=raise_node.lineno,
                        column=raise_node.col_offset,
                    ),
                    end_location=Location(
                        row=raise_node.end_lineno or raise_node.lineno,
                        column=raise_node.end_col_offset or raise_node.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title="Add explicit exception chaining",
                        replacement=(
                            f"raise ... from {caught_name or 'e'}"
                        ),
                        explanation=(
                            "Python 3's exception chaining (PEP 3134) preserves the full "
                            "error context when you use `raise NewError() from original_error`. "
                            "Without `from`, the original traceback is lost, making debugging harder. "
                            "Use `from None` if you intentionally want to suppress the context."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations

    @staticmethod
    def _describe_raised(exc: ast.expr) -> str:
        if isinstance(exc, ast.Call):
            if isinstance(exc.func, ast.Name):
                return f"`{exc.func.id}(...)`"
            if isinstance(exc.func, ast.Attribute):
                return f"`{exc.func.attr}(...)`"
        if isinstance(exc, ast.Name):
            return f"`{exc.id}`"
        return "new exception"
