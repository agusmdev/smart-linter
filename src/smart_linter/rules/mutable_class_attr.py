"""MAIN001: Detect mutable class-level attributes shared across all instances."""

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

# Mutable constructors that produce shared mutable objects when used at class level.
_MUTABLE_CONSTRUCTORS = frozenset({"list", "dict", "set", "defaultdict", "OrderedDict"})

# Base/decorator names that indicate frameworks which handle mutable defaults correctly.
_PYDANTIC_BASE_NAMES = frozenset({"BaseModel", "Schema", "BaseSettings", "BaseConfig", "DispatchBase"})
_DATACLASS_NAMES = frozenset({"dataclass"})
_SQLALCHEMY_BASE_NAMES = frozenset({"Base", "Model", "DeclarativeBase", "TimeStampMixin"})


def _base_names(bases: list[ast.expr]) -> set[str]:
    """Extract simple names from base class list."""
    names: set[str] = set()
    for base in bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _has_pydantic_base(class_node: ast.ClassDef) -> bool:
    return bool(_base_names(class_node.bases) & _PYDANTIC_BASE_NAMES)


def _has_dataclass_decorator(class_node: ast.ClassDef) -> bool:
    for dec in class_node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in _DATACLASS_NAMES:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr in _DATACLASS_NAMES:
            return True
        if isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name) and func.id in _DATACLASS_NAMES:
                return True
            if isinstance(func, ast.Attribute) and func.attr in _DATACLASS_NAMES:
                return True
    return False


def _has_sqlalchemy_base(class_node: ast.ClassDef) -> bool:
    return bool(_base_names(class_node.bases) & _SQLALCHEMY_BASE_NAMES)


def _is_mutable_literal(node: ast.expr) -> bool:
    return isinstance(node, (ast.List, ast.Dict, ast.Set))


def _is_mutable_constructor(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id in _MUTABLE_CONSTRUCTORS:
        return True
    return bool(isinstance(func, ast.Attribute) and func.attr in _MUTABLE_CONSTRUCTORS)


def _is_mutable_value(node: ast.expr) -> bool:
    return _is_mutable_literal(node) or _is_mutable_constructor(node)


def _class_has_slots(class_node: ast.ClassDef) -> bool:
    for stmt in class_node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "__slots__":
                    return True
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "__slots__":
            return True
    return False


def _get_target_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


class MutableClassAttrRule(Rule):
    id: ClassVar[str] = "MAIN001"
    description: ClassVar[str] = "Mutable class attribute shared across all instances — define in __init__ instead"
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("bug", "maintainability")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "class " in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        class_nodes = node_index.get(ast.ClassDef, []) if node_index else []
        if not class_nodes:
            class_nodes = (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))

        for node in class_nodes:
            if _class_has_slots(node):
                continue

            if _has_pydantic_base(node) or _has_dataclass_decorator(node) or _has_sqlalchemy_base(node):
                continue

            self._check_class_body(node, filename, violations)

        return violations

    def _check_class_body(
        self,
        class_node: ast.ClassDef,
        filename: str,
        violations: list[Violation],
    ) -> None:
        for stmt in class_node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    name = _get_target_name(target)
                    if name is None or name.startswith("_"):
                        continue
                    if _is_mutable_value(stmt.value):
                        violations.append(self._make_violation(name=name, node=stmt, filename=filename))

            if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                if class_node.bases:
                    continue
                name = _get_target_name(stmt.target)
                if name is not None and not name.startswith("_") and _is_mutable_value(stmt.value):
                    violations.append(self._make_violation(name=name, node=stmt, filename=filename))

    def _make_violation(
        self,
        name: str,
        node: ast.stmt,
        filename: str,
    ) -> Violation:
        return Violation(
            rule_id=self.id,
            message=(
                f"Mutable class attribute `{name}` shared across all instances "
                f"of the class — define in `__init__` instead"
            ),
            location=Location(row=node.lineno, column=node.col_offset),
            end_location=Location(
                row=node.end_lineno or node.lineno,
                column=node.end_col_offset or node.col_offset,
            ),
            severity=self.severity,
            fix=FixSuggestion(
                title=f"Move `{name}` to __init__",
                replacement=f"self.{name} = ...  # in __init__",
                explanation=(
                    f"Mutable class attributes are shared across all instances. "
                    f"Defining `{name}` in `__init__` ensures each instance "
                    f"has its own copy."
                ),
            ),
            filename=filename,
        )
