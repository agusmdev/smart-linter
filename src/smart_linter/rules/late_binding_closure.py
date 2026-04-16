"""MAIN002: Detect closures that capture loop variables by reference."""

from __future__ import annotations

import ast
from typing import ClassVar, cast

from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)


def _extract_target_names(target: ast.expr) -> list[str]:
    """Extract variable names from a for-loop target (handles tuple unpacking)."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, ast.Tuple):
        names: list[str] = []
        for elt in target.elts:
            names.extend(_extract_target_names(elt))
        return names
    return []


def _get_closure_param_names(
    node: ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    """Get the set of parameter names defined by the closure."""
    names: set[str] = set()
    args = node.args
    for arg in args.args:
        names.add(arg.arg)
    for arg in args.posonlyargs:
        names.add(arg.arg)
    for arg in args.kwonlyargs:
        names.add(arg.arg)
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _get_default_captured_names(
    node: ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef,
) -> set[str]:
    """Variable names captured by-value via ``var=var`` default arguments."""
    captured: set[str] = set()
    args = node.args

    paired: list[tuple[ast.arg, ast.expr | None]] = list(
        zip(args.args[-len(args.defaults) :], args.defaults, strict=False)
    )
    paired += list(zip(args.kwonlyargs[-len(args.kw_defaults) :], args.kw_defaults, strict=False))

    for param, default in paired:
        if default is not None and isinstance(default, ast.Name) and default.id == param.arg:
            captured.add(param.arg)
    return captured


def _names_in_body(
    node: ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef,
    loop_var_names: set[str],
    param_names: set[str],
    default_captured: set[str],
) -> list[tuple[str, ast.Name]]:
    excluded = param_names | default_captured
    body = node.body
    if isinstance(body, list):
        nodes = cast(list[ast.AST], body)
    else:
        nodes: list[ast.AST] = [body]

    references: list[tuple[str, ast.Name]] = []
    for target in nodes:
        for child in ast.walk(target):
            if (
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id in loop_var_names
                and child.id not in excluded
            ):
                references.append((child.id, child))
    return references


class LateBindingClosureRule(Rule):
    id: ClassVar[str] = "MAIN002"
    description: ClassVar[str] = (
        "Closure captures loop variable by reference — use default argument to capture by value"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("bug", "logic")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "for " in source or "while " in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []
        self._check_node(tree, set(), filename, violations)
        return violations

    def _check_node(
        self,
        node: ast.AST,
        outer_loop_vars: set[str],
        filename: str,
        violations: list[Violation],
    ) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.AsyncFor)):
                self._check_loop(child, outer_loop_vars, filename, violations)
            elif isinstance(child, ast.While):
                self._check_while_loop(child, outer_loop_vars, filename, violations)
            else:
                self._check_node(child, outer_loop_vars, filename, violations)

    def _check_loop(
        self,
        loop: ast.For | ast.AsyncFor,
        outer_loop_vars: set[str],
        filename: str,
        violations: list[Violation],
    ) -> None:
        loop_var_names = set(_extract_target_names(loop.target))
        all_loop_vars = outer_loop_vars | loop_var_names

        self._check_body_for_closures(loop.body, all_loop_vars, filename, violations)

        for stmt in loop.body:
            self._check_node(stmt, all_loop_vars, filename, violations)

        if loop.orelse:
            self._check_body_for_closures(loop.orelse, all_loop_vars, filename, violations)
            for stmt in loop.orelse:
                self._check_node(stmt, all_loop_vars, filename, violations)

    def _check_while_loop(
        self,
        loop: ast.While,
        outer_loop_vars: set[str],
        filename: str,
        violations: list[Violation],
    ) -> None:
        self._check_body_for_closures(loop.body, outer_loop_vars, filename, violations)

        for stmt in loop.body:
            self._check_node(stmt, outer_loop_vars, filename, violations)

        if loop.orelse:  # pragma: no cover
            self._check_body_for_closures(loop.orelse, outer_loop_vars, filename, violations)
            for stmt in loop.orelse:
                self._check_node(stmt, outer_loop_vars, filename, violations)

    def _check_body_for_closures(
        self,
        body: list[ast.stmt],
        loop_var_names: set[str],
        filename: str,
        violations: list[Violation],
    ) -> None:
        if not loop_var_names:
            return

        for stmt in body:
            for node in ast.walk(stmt):
                if not isinstance(node, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue

                param_names = _get_closure_param_names(node)
                default_captured = _get_default_captured_names(node)
                refs = _names_in_body(node, loop_var_names, param_names, default_captured)

                for var_name, name_node in refs:
                    violations.append(
                        self._make_violation(
                            var_name=var_name,
                            closure_node=node,
                            name_node=name_node,
                            filename=filename,
                        )
                    )

    def _make_violation(
        self,
        var_name: str,
        closure_node: ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef,
        name_node: ast.Name,
        filename: str,
    ) -> Violation:
        if isinstance(closure_node, ast.Lambda):
            closure_kind = "lambda"
        elif isinstance(closure_node, ast.AsyncFunctionDef):
            closure_kind = f"async def `{closure_node.name}`"
        else:
            closure_kind = f"def `{closure_node.name}`"

        return Violation(
            rule_id=self.id,
            message=(
                f"{closure_kind} captures loop variable `{var_name}` by reference "
                f"— use default argument to capture by value"
            ),
            location=Location(
                row=closure_node.lineno,
                column=closure_node.col_offset,
            ),
            end_location=Location(
                row=closure_node.end_lineno or closure_node.lineno,
                column=closure_node.end_col_offset or closure_node.col_offset,
            ),
            severity=self.severity,
            fix=FixSuggestion(
                title=f"Capture `{var_name}` by value using default argument",
                replacement=f"{var_name}={var_name}",
                explanation=(
                    f"Closures capture variables by reference. When the loop completes, "
                    f"all closures reference the final value of `{var_name}`. "
                    f"Use `{var_name}={var_name}` in the parameter list to capture "
                    f"the current value on each iteration."
                ),
            ),
            filename=filename,
        )
