"""RES001: Detect resources opened without context manager — risk of resource leak."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from typing import ClassVar

from smart_linter.ast_utils import get_qualified_name as _qname
from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)

# ── Known resource-creating call patterns ──────────────────────────────────

# (module_path | bare_name, attribute_or_None)
_RESOURCE_PATTERNS: frozenset[tuple[str, str | None]] = frozenset(
    {
        # builtin
        ("open", None),
        # httpx
        ("httpx", "Client"),
        ("httpx", "AsyncClient"),
        # urllib
        ("urllib.request", "urlopen"),
        # subprocess
        ("subprocess", "Popen"),
        # socket
        ("socket", "socket"),
        # sqlite3
        ("sqlite3", "connect"),
        # psycopg2
        ("psycopg2", "connect"),
        # mysql
        ("mysql.connector", "connect"),
        # redis
        ("redis", "Redis"),
        ("redis", "StrictRedis"),
    }
)


def _is_resource_call(call: ast.Call) -> str | None:
    """Return a human-readable name if *call* creates a known resource, else None."""
    func = call.func

    # Handle bare name calls: open(...)
    if isinstance(func, ast.Name):
        for module, attr in _RESOURCE_PATTERNS:
            if attr is None and func.id == module:
                return module
        return None

    # Handle attribute calls: httpx.Client(), urllib.request.urlopen()
    if isinstance(func, ast.Attribute):
        caller = _qname(func.value)
        if caller is not None:
            for module, attr in _RESOURCE_PATTERNS:
                if attr is not None and caller == module and func.attr == attr:
                    return f"{caller}.{func.attr}"
                if attr is None and caller == module:
                    return caller
        return None

    return None


# ── Enclosing scope helpers ────────────────────────────────────────────────


def _find_enclosing_body(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> list[ast.stmt] | None:
    """Return the statement list of the enclosing function/class/module body."""
    current: ast.AST | None = node
    while current is not None:
        parent = parent_map.get(current)
        if parent is None:
            # top-level module
            return None  # will be handled by walking the whole tree
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent.body
        if isinstance(parent, ast.ClassDef):
            return parent.body
        current = parent
    return None  # pragma: no cover


def _get_module_body(tree: ast.Module) -> list[ast.stmt]:
    return tree.body


# ── Safety checks ──────────────────────────────────────────────────────────


def _is_inside_with_context(assign_node: ast.Assign, parent_map: dict[ast.AST, ast.AST]) -> bool:
    """True if the assignment itself is the context expression of a `with` statement.

    Example that returns True::

        with open(...) as f:   # the Call is the context_expr
    """
    parent = parent_map.get(assign_node)
    if isinstance(parent, ast.With):
        for item in parent.items:
            if item.context_expr is assign_node.value:
                return True
    return False


def _var_name(node: ast.Assign) -> str | None:
    """Extract the simple variable name from the first target of an assignment."""
    if assign_targets := node.targets:
        target = assign_targets[0]
        if isinstance(target, ast.Name):
            return target.id
    return None


_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _walk_stmts_shallow(stmts: list[ast.stmt]) -> Iterator[ast.AST]:
    for stmt in stmts:
        if isinstance(stmt, _SCOPE_BOUNDARIES):
            continue
        yield from _walk_no_nested_scopes(stmt)


def _walk_no_nested_scopes(node: ast.AST) -> Iterator[ast.AST]:
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_BOUNDARIES):
            continue
        yield from _walk_no_nested_scopes(child)


def _var_used_in_with(var: str, stmts: list[ast.stmt]) -> bool:
    """True if *var* appears as a context expression in a `with` item."""
    for node in _walk_stmts_shallow(stmts):
        if isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.context_expr, ast.Name) and item.context_expr.id == var:
                    return True
    return False


def _var_returned(var: str, stmts: list[ast.stmt]) -> bool:
    """True if *var* is the operand of a `return` statement."""
    for node in _walk_stmts_shallow(stmts):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id == var:
            return True
    return False


def _var_yielded(var: str, stmts: list[ast.stmt]) -> bool:
    """True if *var* is the operand of a `yield` expression."""
    for node in _walk_stmts_shallow(stmts):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Yield):
            val = node.value.value
            if isinstance(val, ast.Name) and val.id == var:
                return True
        # yield from
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.YieldFrom):
            val = node.value.value
            if isinstance(val, ast.Name) and val.id == var:
                return True
    return False


def _var_closed_in_finally(var: str, stmts: list[ast.stmt]) -> bool:
    """True if ``<var>.close()`` is called inside a ``finally`` block."""
    for node in _walk_stmts_shallow(stmts):
        if isinstance(node, ast.Try) and node.finalbody:
            for finally_stmt in node.finalbody:
                for sub in ast.walk(finally_stmt):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and (
                            sub.func.attr == "close"
                            and isinstance(sub.func.value, ast.Name)
                            and sub.func.value.id == var
                        )
                    ):
                        return True
        # Python 3.11+ TryStar also has finalbody
        if hasattr(ast, "TryStar") and isinstance(node, ast.TryStar) and node.finalbody:
            for finally_stmt in node.finalbody:
                for sub in ast.walk(finally_stmt):
                    if (
                        isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and (
                            sub.func.attr == "close"
                            and isinstance(sub.func.value, ast.Name)
                            and sub.func.value.id == var
                        )
                    ):
                        return True
    return False


def _is_safe(var: str, stmts: list[ast.stmt]) -> bool:
    """Return True if the variable is managed safely somewhere in *stmts*."""
    return (
        _var_used_in_with(var, stmts)
        or _var_returned(var, stmts)
        or _var_yielded(var, stmts)
        or _var_closed_in_finally(var, stmts)
    )


# ── Rule implementation ────────────────────────────────────────────────────


class UnclosedResourceRule(Rule):
    id: ClassVar[str] = "RES001"
    description: ClassVar[str] = "Resource opened without context manager — use 'with' statement to ensure cleanup"
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("reliability", "resource-leak", "bug")

    @classmethod
    def should_check(cls, source: str) -> bool:
        """Quick string scan — skip files unlikely to create resources."""
        hints = (
            "open(",
            "Client()",
            "AsyncClient()",
            "urlopen(",
            "Popen(",
            "socket(",
            "connect(",
            "Redis()",
            "StrictRedis()",
        )
        return any(h in source for h in hints)

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        # Collect all scope bodies: module-level and every function/method
        scope_bodies: dict[int, list[ast.stmt]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope_bodies[id(node)] = node.body

        # Build parent map for context detection
        parent_map: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[child] = parent

        # Walk all scope bodies and check assignments
        for _scope_id, stmts in scope_bodies.items():
            self._check_scope(stmts, parent_map, filename, violations)

        return violations

    def _check_scope(
        self,
        stmts: list[ast.stmt],
        parent_map: dict[ast.AST, ast.AST],
        filename: str,
        violations: list[Violation],
    ) -> None:
        for node in _walk_stmts_shallow(stmts):
            if not isinstance(node, ast.Assign):
                continue

            # Must assign a call result
            if not isinstance(node.value, ast.Call):
                continue

            # Call must create a known resource
            resource_name = _is_resource_call(node.value)
            if resource_name is None:
                continue

            # Already inside a `with` context expression → safe
            if _is_inside_with_context(node, parent_map):  # pragma: no cover
                continue

            var = _var_name(node)
            if var is None:
                continue

            # Check safety measures in the same scope body
            if _is_safe(var, stmts):
                continue

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Resource `{resource_name}()` assigned to `{var}` "
                        f"without context manager — use a 'with' statement "
                        f"to ensure cleanup"
                    ),
                    location=Location(row=node.lineno, column=node.col_offset),
                    end_location=Location(
                        row=node.end_lineno or node.lineno,
                        column=node.end_col_offset or node.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title="Use 'with' statement for resource management",
                        replacement=f"with {resource_name}(...) as {var}:",
                        explanation=(
                            "Resources opened without 'with' may leak if an "
                            "exception occurs before .close() is called. "
                            "Context managers ensure cleanup even on exceptions."
                        ),
                    ),
                    filename=filename,
                )
            )
