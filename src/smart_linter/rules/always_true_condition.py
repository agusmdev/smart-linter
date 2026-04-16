"""LOGIC001: Detect always-true or always-false boolean conditions."""

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


def _get_variable_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _get_negated_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Name):
        return node.operand.id
    return None


def _are_same_var(a: ast.expr, b: ast.expr) -> bool:
    name_a = _get_variable_name(a)
    name_b = _get_variable_name(b)
    return name_a is not None and name_a == name_b


def _is_tautological_boolop(
    node: ast.BoolOp,
) -> tuple[bool, str, str, FixSuggestion | None]:
    """Returns (is_issue, message_fragment, kind, fix)."""
    values = node.values
    op = node.op

    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            vi, vj = values[i], values[j]

            if _are_same_var(vi, vj):
                var = _get_variable_name(vi)
                if isinstance(op, ast.And):
                    return (
                        True,
                        f"`{var} and {var}`",
                        "duplicate",
                        FixSuggestion(
                            title="Remove duplicate condition",
                            replacement=var,
                            explanation=(f"`{var} and {var}` is always `{var}`. Remove the duplicate operand."),
                        ),
                    )
                else:
                    return (
                        True,
                        f"`{var} or {var}`",
                        "duplicate",
                        FixSuggestion(
                            title="Remove duplicate condition",
                            replacement=var,
                            explanation=(f"`{var} or {var}` is always `{var}`. Remove the duplicate operand."),
                        ),
                    )

            name_i = _get_variable_name(vi)
            neg_j = _get_negated_name(vj)
            neg_i = _get_negated_name(vi)
            name_j = _get_variable_name(vj)

            if isinstance(op, ast.And):
                if name_i and neg_j and name_i == neg_j:
                    var = name_i
                    return (
                        True,
                        f"`{var} and not {var}`",
                        "contradiction",
                        FixSuggestion(
                            title="Condition is always false — check logic",
                            replacement="False",
                            explanation=(f"`{var} and not {var}` is always `False`. Review the intended logic."),
                        ),
                    )
                if neg_i and name_j and neg_i == name_j:
                    var = name_j
                    return (
                        True,
                        f"`not {var} and {var}`",
                        "contradiction",
                        FixSuggestion(
                            title="Condition is always false — check logic",
                            replacement="False",
                            explanation=(f"`not {var} and {var}` is always `False`. Review the intended logic."),
                        ),
                    )
            else:
                if name_i and neg_j and name_i == neg_j:
                    var = name_i
                    return (
                        True,
                        f"`{var} or not {var}`",
                        "tautology",
                        FixSuggestion(
                            title="Condition is always true — check logic",
                            replacement="True",
                            explanation=(f"`{var} or not {var}` is always `True`. Review the intended logic."),
                        ),
                    )
                if neg_i and name_j and neg_i == name_j:
                    var = name_j
                    return (
                        True,
                        f"`not {var} or {var}`",
                        "tautology",
                        FixSuggestion(
                            title="Condition is always true — check logic",
                            replacement="True",
                            explanation=(f"`not {var} or {var}` is always `True`. Review the intended logic."),
                        ),
                    )

    return (False, "", "", None)  # type: ignore[return-value]


def _is_tautological_compare(
    node: ast.Compare,
) -> tuple[bool, str, str, FixSuggestion | None]:
    """Returns (is_issue, message_fragment, kind, fix)."""
    left = node.left
    for op, comparator in zip(node.ops, node.comparators, strict=False):
        if not _are_same_var(left, comparator):
            left = comparator
            continue

        var = _get_variable_name(left)  # type: ignore[arg-type]

        if isinstance(op, ast.Eq):
            return (
                True,
                f"`{var} == {var}`",
                "self-eq",
                FixSuggestion(
                    title="Self-comparison is always true — likely a typo",
                    replacement=var,
                    explanation=(
                        f"`{var} == {var}` is always `True`. Did you mean to compare two different variables?"
                    ),
                ),
            )

        if isinstance(op, ast.NotEq):
            return (
                True,
                f"`{var} != {var}`",
                "self-neq",
                FixSuggestion(
                    title="Self-comparison is always false — likely a typo",
                    replacement="False",
                    explanation=(
                        f"`{var} != {var}` is always `False` "
                        "(except for `float('nan')`). "
                        "Did you mean to compare two different variables?"
                    ),
                ),
            )

        if isinstance(op, ast.Is):
            return (
                True,
                f"`{var} is {var}`",
                "self-is",
                FixSuggestion(
                    title="`x is x` is always true for most objects",
                    replacement=var,
                    explanation=(
                        f"`{var} is {var}` is always `True` for most objects. "
                        "If checking identity is intentional, this is fine; "
                        "otherwise it may be a typo."
                    ),
                ),
            )

        left = comparator

    return (False, "", "", None)


def _is_isinstance_type_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Name) or node.func.id != "isinstance":
        return False
    if len(node.args) != 2:
        return False
    second = node.args[1]
    if not isinstance(second, ast.Call):
        return False
    if not isinstance(second.func, ast.Name) or second.func.id != "type":
        return False
    if len(second.args) != 1:
        return False
    first_arg = node.args[0]
    type_arg = second.args[0]
    return _are_same_var(first_arg, type_arg)


def _collect_conditions(tree: ast.AST) -> list[ast.expr]:
    conditions: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.While, ast.IfExp, ast.Assert)):
            conditions.append(node.test)
    return conditions


class AlwaysTrueConditionRule(Rule):
    id: ClassVar[str] = "LOGIC001"
    description: ClassVar[str] = "Condition is always true or always false — likely a logic error"
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("bug", "logic")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return any(kw in source for kw in ("if ", "while ", "assert ", " if "))

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []
        node_index = getattr(self, "_node_index", None)

        if node_index:
            conditions = []
            for t in (ast.If, ast.While, ast.IfExp, ast.Assert):
                for node in node_index.get(t, []):
                    conditions.append(node.test)
        else:
            conditions = _collect_conditions(tree)

        for cond in conditions:
            self._check_expr(cond, filename, violations)

        return violations

    def _check_expr(
        self,
        node: ast.expr,
        filename: str,
        violations: list[Violation],
    ) -> None:
        if isinstance(node, ast.BoolOp):
            found, fragment, kind, fix = _is_tautological_boolop(node)
            if found:
                assert fix is not None
                self._add(violations, node, fragment, kind, fix, filename)
            for val in node.values:
                self._check_expr(val, filename, violations)
            return

        if isinstance(node, ast.Compare):
            found, fragment, kind, fix = _is_tautological_compare(node)
            if found:
                assert fix is not None
                self._add(violations, node, fragment, kind, fix, filename)
            return

        if _is_isinstance_type_call(node):
            assert isinstance(node, ast.Call)
            var = _get_variable_name(node.args[0])
            self._add(
                violations,
                node,
                f"`isinstance({var}, type({var}))`",
                "isinstance-type",
                FixSuggestion(
                    title="`isinstance(x, type(x))` is always true",
                    replacement=var,
                    explanation=(
                        f"`isinstance({var}, type({var}))` is always `True`. Use a concrete type or remove the check."
                    ),
                ),
                filename,
            )
            return

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self._check_expr(node.operand, filename, violations)
            return

    @staticmethod
    def _add(
        violations: list[Violation],
        node: ast.expr,
        fragment: str,
        kind: str,
        fix: FixSuggestion,
        filename: str,
    ) -> None:
        label = (
            "always true"
            if kind
            in (
                "duplicate",
                "self-eq",
                "self-is",
                "tautology",
                "isinstance-type",
            )
            else "always false"
        )
        violations.append(
            Violation(
                rule_id="LOGIC001",
                message=f"Condition {fragment} is {label} — likely a logic error",
                location=Location(row=node.lineno, column=node.col_offset),
                end_location=Location(
                    row=node.end_lineno or node.lineno,
                    column=node.end_col_offset or node.col_offset,
                ),
                severity=Severity.WARNING,
                fix=fix,
                filename=filename,
            )
        )
