"""ERR001: Detects exception handlers that silently swallow errors."""

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

# Names/prefixes that indicate meaningful exception handling when called.
_MEANINGFUL_CALL_PREFIXES: frozenset[str] = frozenset(
    {
        "logging.debug",
        "logging.info",
        "logging.warning",
        "logging.error",
        "logging.critical",
        "logging.exception",
        "logging.log",
        "log.debug",
        "log.info",
        "log.warning",
        "log.error",
        "log.critical",
        "log.exception",
        "log.log",
        "logger.debug",
        "logger.info",
        "logger.warning",
        "logger.error",
        "logger.critical",
        "logger.exception",
        "logger.log",
        "sys.exit",
        "warnings.warn",
        "print",
        "traceback.print_exc",
        "traceback.format_exc",
    }
)

# Framework exceptions commonly used for control flow where `pass` is
# intentional (e.g. FastAPI HTTPException in permission checks).
_CONTROL_FLOW_EXCEPTIONS: frozenset[str] = frozenset({"HTTPException"})


def _get_qualified_name(node: ast.expr) -> str | None:
    """Return dotted name for Name/Attribute nodes, e.g. 'logging.error'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


def _is_meaningful_call(node: ast.expr) -> bool:
    """Check whether a call func expression is a known meaningful call."""
    name = _get_qualified_name(node)
    if name is None:
        return False
    if name in _MEANINGFUL_CALL_PREFIXES:
        return True
    for prefix in _MEANINGFUL_CALL_PREFIXES:
        if name.startswith(prefix + ".") or name.startswith(prefix + "("):
            return True
    parts = name.split(".")
    if len(parts) >= 2:
        root = parts[0]
        if root in ("logging", "logger", "log") and parts[-1] not in (
            "getLogger",
            "Logger",
            "FileHandler",
            "StreamHandler",
        ):
            return True
    return False


def _has_meaningful_action(body: list[ast.stmt]) -> bool:
    """Return True if the handler body contains any meaningful action."""
    for stmt in body:
        if isinstance(stmt, ast.Raise):
            return True
        if isinstance(stmt, ast.Return):
            return True
        if isinstance(stmt, (ast.Continue, ast.Break)):
            return True
        if isinstance(stmt, ast.Expr):
            if isinstance(stmt.value, ast.Call):
                if _is_meaningful_call(stmt.value.func):
                    return True
                continue
            if isinstance(stmt.value, ast.Constant) and stmt.value.value is ...:
                continue
            continue
        if isinstance(stmt, ast.Assign):
            if any(isinstance(v, ast.Call) for v in _iter_assign_values(stmt)):
                return True
            if _has_uppercase_target(stmt):
                return True
            continue
        if isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.value, ast.Call):
                return True
            continue
        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None and isinstance(stmt.value, ast.Call):
                return True
            continue
        if isinstance(stmt, ast.Pass):
            continue
        return True
    return False


def _has_uppercase_target(stmt: ast.Assign) -> bool:
    return any(isinstance(target, ast.Name) and target.id.isupper() for target in stmt.targets)


def _iter_assign_values(stmt: ast.Assign) -> list[ast.expr]:
    values: list[ast.expr] = []
    if isinstance(stmt.value, (ast.Tuple, ast.List)):
        values.extend(stmt.value.elts)
    else:
        values.append(stmt.value)
    return values


def _is_control_flow_exception(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    if isinstance(handler.type, ast.Name):
        return handler.type.id in _CONTROL_FLOW_EXCEPTIONS
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id in _CONTROL_FLOW_EXCEPTIONS
            for elt in handler.type.elts
        )
    return False


class SilentExceptionRule(Rule):
    """ERR001: Flags except handlers that silently swallow exceptions."""

    id: ClassVar[str] = "ERR001"
    description: ClassVar[str] = (
        "Exception handler silently swallows errors without logging or re-raising"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("error-handling", "reliability", "bug")

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if self._is_silent_handler(handler):
                    violations.append(self._make_violation(handler, filename))
        return violations

    def _is_silent_handler(self, handler: ast.ExceptHandler) -> bool:
        """Return True if the handler body is effectively silent."""
        body = handler.body
        if not body:
            return True
        if _is_control_flow_exception(handler):
            return False
        return not _has_meaningful_action(body)

    def _make_violation(self, handler: ast.ExceptHandler, filename: str) -> Violation:
        exc_type = self._describe_exc_type(handler)
        message = (
            f"Exception handler for `{exc_type}` silently swallows errors "
            f"without logging or re-raising"
        )
        return Violation(
            rule_id=self.id,
            message=message,
            location=Location(row=handler.lineno, column=handler.col_offset),
            end_location=Location(
                row=handler.end_lineno or handler.lineno,
                column=(handler.end_col_offset or handler.col_offset),
            ),
            severity=self.severity,
            fix=self._build_fix(handler),
            filename=filename,
        )

    @staticmethod
    def _describe_exc_type(handler: ast.ExceptHandler) -> str:
        if handler.type is None:
            return "bare except"
        return (
            ast.dump(handler.type)
            if not isinstance(handler.type, ast.Name)
            else handler.type.id
        )

    def _build_fix(self, handler: ast.ExceptHandler) -> FixSuggestion:
        is_bare = handler.type is None
        is_broad = isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
        name_part = ""
        if handler.name:
            name_part = f" as {handler.name}"

        if is_bare:
            return FixSuggestion(
                title="Replace bare except with specific exception type or add logging",
                replacement=(
                    f'except SpecificError{name_part}:\n    logger.exception("...")'
                ),
                explanation=(
                    "Bare except catches SystemExit and KeyboardInterrupt. "
                    "PEP 760 deprecates bare except in Python 3.14+."
                ),
            )

        exc_id = (
            handler.type.id if isinstance(handler.type, ast.Name) else "SpecificError"
        )

        if is_broad:
            return FixSuggestion(
                title="Add logging or re-raise the exception",
                replacement=(
                    f"except Exception{name_part}:\n"
                    f'    logger.exception("Description of what failed")'
                ),
                explanation=(
                    "Silently swallowing exceptions hides bugs. "
                    "At minimum, log the error."
                ),
            )

        return FixSuggestion(
            title=f"Handle `{exc_id}` or log it",
            replacement=(f'except {exc_id}{name_part}:\n    logger.warning("...")'),
            explanation=(
                "Empty exception handlers hide failures. "
                "Add logging or handle the error properly."
            ),
        )
