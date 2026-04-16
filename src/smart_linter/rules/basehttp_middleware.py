"""FAST001: Detect BaseHTTPMiddleware usage — use pure ASGI middleware instead.

BaseHTTPMiddleware adds significant overhead because it wraps the entire
request/response cycle in a context switch. For high-throughput applications,
pure ASGI middleware is recommended.

This is documented in the Starlette docs and FastAPI community as a known
performance anti-pattern. Ruff cannot detect this because it requires
understanding class inheritance semantics.
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


class BaseHTTPMiddlewareRule(Rule):
    id: ClassVar[str] = "FAST001"
    description: ClassVar[str] = (
        "BaseHTTPMiddleware adds overhead — use pure ASGI middleware for better performance"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("fastapi", "performance", "middleware")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "BaseHTTPMiddleware" in source or "basehttpmiddleware" in source.lower()

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        class_nodes = node_index.get(ast.ClassDef, []) if node_index else []
        if not class_nodes:
            class_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

        for node in class_nodes:
            if not isinstance(node, ast.ClassDef):
                continue

            # Check if class inherits from BaseHTTPMiddleware
            for base in node.bases:
                base_name = self._get_name(base)
                if base_name == "BaseHTTPMiddleware":
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=(
                                f"Class `{node.name}` inherits from `BaseHTTPMiddleware`, "
                                f"which adds overhead from request/response wrapping. "
                                f"For production use, implement pure ASGI middleware instead."
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
                                title=f"Convert `{node.name}` to pure ASGI middleware",
                                replacement=(
                                    "class PureASGIMiddleware:\n"
                                    "    def __init__(self, app):\n"
                                    "        self.app = app\n"
                                    "\n"
                                    "    async def __call__(self, scope, receive, send):\n"
                                    "        if scope['type'] != 'http':\n"
                                    "            await self.app(scope, receive, send)\n"
                                    "            return\n"
                                    "        # Your middleware logic here\n"
                                    "        await self.app(scope, receive, send)"
                                ),
                                explanation=(
                                    "BaseHTTPMiddleware creates an intermediate response, "
                                    "adding memory overhead and latency. Pure ASGI middleware "
                                    "operates directly on the ASGI scope, which is significantly "
                                    "faster. See: https://github.com/encode/starlette/issues/919"
                                ),
                            ),
                            filename=filename,
                        )
                    )
                    break  # Only flag once per class

        return violations

    @staticmethod
    def _get_name(node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None
