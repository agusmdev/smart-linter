"""ASYNC003: Detect async functions that never await anything.

Functions declared as `async def` that contain no `await`, `async for`, or
`async with` statements are running on the event loop unnecessarily. In
FastAPI, this means the endpoint blocks the event loop instead of running
in a threadpool (which happens for regular `def` endpoints).

This is a common mistake when developers add `async` without understanding
its implications, or when async calls are removed during refactoring but
the `async` keyword is forgotten.
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


def _has_async_operations(func: ast.AsyncFunctionDef) -> bool:
    """Check if an async function has any async operations.

    Looks for:
    - await expressions
    - async with statements
    - async for loops
    """
    for node in ast.walk(func):
        # Don't look inside nested function definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not func:
            continue

        if isinstance(node, ast.Await):
            return True
        if isinstance(node, ast.AsyncWith):
            return True
        if isinstance(node, ast.AsyncFor):
            return True

    return False


def _has_nested_async_func(func: ast.AsyncFunctionDef) -> bool:
    """Check if function defines nested async functions (which might be the intent)."""
    for node in ast.walk(func):
        if isinstance(node, ast.AsyncFunctionDef) and node is not func:
            return True
    return False


class AsyncNoAwaitRule(Rule):
    id: ClassVar[str] = "ASYNC003"
    description: ClassVar[str] = (
        "Async function has no await, async for, or async with — use regular `def` instead"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("async", "performance", "fastapi")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "async def" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        async_funcs = node_index.get(ast.AsyncFunctionDef, []) if node_index else []
        if not async_funcs:
            async_funcs = [
                n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
            ]

        for func in async_funcs:
            if not isinstance(func, ast.AsyncFunctionDef):
                continue

            # Skip if function has async operations
            if _has_async_operations(func):
                continue

            # Skip if function defines nested async functions
            if _has_nested_async_func(func):
                continue

            # Skip dunder methods and fixtures
            if func.name.startswith("__") and func.name.endswith("__"):
                continue
            if func.name.startswith("test_"):
                continue

            message = (
                f"Async function `{func.name}` has no `await`, `async for`, or "
                f"`async with` statements. Use regular `def` instead to avoid "
                f"unnecessary event loop overhead."
            )

            # Check if it looks like a FastAPI endpoint
            is_endpoint = any(
                _is_endpoint_decorator(d) for d in func.decorator_list
            )
            if is_endpoint:
                message += (
                    " In FastAPI, regular `def` endpoints run in a threadpool, "
                    "which is better for CPU-bound or sync I/O operations."
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
                        title=f"Change `async def {func.name}` to `def {func.name}`",
                        replacement=f"def {func.name}(...):",
                        explanation=(
                            "Without `await`, an async function gains nothing from being async. "
                            "In FastAPI, regular `def` endpoints are automatically run in a "
                            "threadpool, preventing event loop blocking. Only use `async def` "
                            "when the function performs actual async I/O (database queries, "
                            "HTTP requests, file I/O via aiofiles, etc.)."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations


HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "options", "head"})


def _is_endpoint_decorator(decorator: ast.expr) -> bool:
    """Check if the decorator is a FastAPI endpoint decorator."""
    if isinstance(decorator, ast.Call):
        func = decorator.func
    elif isinstance(decorator, ast.Attribute):
        func = decorator
    else:
        return False

    if isinstance(func, ast.Attribute):
        return func.attr.lower() in HTTP_METHODS
    return False
