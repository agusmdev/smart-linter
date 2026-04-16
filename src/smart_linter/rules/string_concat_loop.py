"""PERF001: Detect string concatenation using += inside loops (O(n²) pattern)."""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.ast_utils import build_parent_map
from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)

_LOOP_TYPES = (ast.For, ast.While, ast.AsyncFor)


def _build_string_init_map(tree: ast.AST) -> dict[str, ast.Assign]:
    """Map variable names that are initialized as ``""`` to their Assign node."""
    init_map: dict[str, ast.Assign] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(node.value, ast.Constant) and node.value.value == "":
            init_map[target.id] = node
    return init_map


def _is_inside_loop(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> bool:
    """Return True if *node* is inside a for/while loop body."""
    parent = parent_map.get(node)
    while parent is not None:
        if isinstance(parent, _LOOP_TYPES):
            return True
        parent = parent_map.get(parent)
    return False


def _is_inside_comprehension(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> bool:
    """Return True if *node* is inside a list/set/dict comprehension or generator."""
    comp_types = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    parent = parent_map.get(node)
    while parent is not None:
        if isinstance(parent, comp_types):
            return True  # pragma: no cover
        parent = parent_map.get(parent)
    return False


class StringConcatLoopRule(Rule):
    id: ClassVar[str] = "PERF001"
    description: ClassVar[str] = (
        "String concatenation using += inside loop creates O(n²) new strings — use list.append() + ''.join() instead"
    )
    severity: ClassVar[Severity] = Severity.INFO
    tags: ClassVar[tuple[str, ...]] = ("performance",)

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        parent_map = getattr(self, "_parent_map", None) or build_parent_map(tree)
        node_index = getattr(self, "_node_index", None)
        violations: list[Violation] = []

        if node_index:
            string_inits = {
                target.id: node
                for node in node_index.get(ast.Assign, [])
                if len(node.targets) == 1
                and isinstance((target := node.targets[0]), ast.Name)
                and isinstance(node.value, ast.Constant)
                and node.value.value == ""
            }

            for node in node_index.get(ast.AugAssign, []):
                if isinstance(node.op, ast.Add):
                    self._check_aug_assign(node, parent_map, string_inits, filename, violations)

            for node in node_index.get(ast.Assign, []):
                if isinstance(node.value, ast.BinOp):
                    self._check_assign_add(node, parent_map, string_inits, filename, violations)
        else:
            string_inits = _build_string_init_map(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
                    self._check_aug_assign(node, parent_map, string_inits, filename, violations)
                elif isinstance(node, ast.Assign) and isinstance(node.value, ast.BinOp):
                    self._check_assign_add(node, parent_map, string_inits, filename, violations)

        return violations

    def _check_aug_assign(
        self,
        node: ast.AugAssign,
        parent_map: dict[ast.AST, ast.AST],
        string_inits: dict[str, ast.Assign],
        filename: str,
        violations: list[Violation],
    ) -> None:
        if not isinstance(node.target, ast.Name):
            return
        var_name = node.target.id

        if not _is_inside_loop(node, parent_map):
            return
        if _is_inside_comprehension(node, parent_map):  # pragma: no cover
            return

        # Only flag if the variable was initialized as ""
        if var_name not in string_inits:
            return

        violations.append(
            self._build_violation(
                var_name=var_name,
                lineno=node.lineno,
                col_offset=node.col_offset,
                end_lineno=node.end_lineno or node.lineno,
                end_col_offset=node.end_col_offset or node.col_offset,
                filename=filename,
            )
        )

    def _check_assign_add(
        self,
        node: ast.Assign,
        parent_map: dict[ast.AST, ast.AST],
        string_inits: dict[str, ast.Assign],
        filename: str,
        violations: list[Violation],
    ) -> None:
        binop = node.value
        assert isinstance(binop, ast.BinOp)
        if not isinstance(binop.op, ast.Add):
            return
        if len(node.targets) != 1:
            return
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            return

        var_name = target.id

        if not isinstance(binop.left, ast.Name) or binop.left.id != var_name:
            return

        if not _is_inside_loop(node, parent_map):
            return
        if _is_inside_comprehension(node, parent_map):  # pragma: no cover
            return

        if var_name not in string_inits:
            return

        violations.append(
            self._build_violation(
                var_name=var_name,
                lineno=node.lineno,
                col_offset=node.col_offset,
                end_lineno=node.end_lineno or node.lineno,
                end_col_offset=node.end_col_offset or node.col_offset,
                filename=filename,
            )
        )

    def _build_violation(
        self,
        var_name: str,
        lineno: int,
        col_offset: int,
        end_lineno: int,
        end_col_offset: int,
        filename: str,
    ) -> Violation:
        return Violation(
            rule_id=self.id,
            message=(
                f"String concatenation using `+=` on `{var_name}` inside loop "
                f"creates O(n²) new strings — use list.append() + ''.join() instead"
            ),
            location=Location(row=lineno, column=col_offset),
            end_location=Location(row=end_lineno, column=end_col_offset),
            severity=self.severity,
            fix=FixSuggestion(
                title="Use list.append() + ''.join() instead of += for string building",
                replacement=f"parts.append(...)\n{var_name} = ''.join(parts)",
                explanation=(
                    "String `+=` in a loop creates a new string object each "
                    "iteration (O(n²)). Using a list with `''.join()` is O(n)."
                ),
            ),
            filename=filename,
        )
