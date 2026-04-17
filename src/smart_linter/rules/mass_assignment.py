"""SEC005: Detect potential mass assignment via **model_dump() / **dict() in ORM constructors.

Passing user input directly to ORM model constructors via **model_dump() or
**dict() can allow attackers to set sensitive fields like is_superuser,
is_active, role, etc. This is the "mass assignment" vulnerability pattern.

The safe approach is to explicitly list allowed fields or use a create schema
that excludes sensitive fields. Ruff cannot detect this because it requires
understanding the relationship between user input schemas and ORM models.
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

# Known ORM base class names
ORM_BASES = frozenset({
    "Base",
    "Model",
    "SQLModel",
    "DeclarativeBase",
})

# Known ORM model name suffixes
ORM_SUFFIXES = ("Model", "Record", "Entity", "Row")

# Sensitive field names that should never be set from user input
SENSITIVE_FIELDS = frozenset({
    "is_superuser",
    "is_active",
    "is_admin",
    "is_staff",
    "is_verified",
    "role",
    "permissions",
    "password",
    "hashed_password",
    "secret",
    "token",
    "api_key",
    "credit_card",
    "ssn",
    "salary",
})


def _get_qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


def _is_model_dump_call(node: ast.expr) -> bool:
    """Check if the expression is a model_dump() or dict() call being unpacked."""
    if isinstance(node, ast.Starred):
        return False
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr in ("model_dump", "dict", "to_dict", "asdict")
        if isinstance(func, ast.Name):
            return func.id in ("model_dump", "dict", "to_dict", "asdict")
    return False


def _is_unpacking_dict(node: ast.keyword) -> bool:
    """Check if the keyword is **model_dump() or **dict() pattern."""
    if node.arg is not None:
        return False  # Not a **kwargs spread
    # In Python AST, **kwargs in a Call appears as keyword with arg=None
    value = node.value
    return _is_model_dump_call(value)


class MassAssignmentRule(Rule):
    id: ClassVar[str] = "SEC005"
    description: ClassVar[str] = (
        "Potential mass assignment: **model_dump()/dict() passed to ORM constructor "
        "may set sensitive fields like is_superuser, role, etc."
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "mass-assignment", "fastapi")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "model_dump" in source or ".dict()" in source or "asdict" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        call_nodes = node_index.get(ast.Call, []) if node_index else []
        if not call_nodes:
            call_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

        for node in call_nodes:
            if not isinstance(node, ast.Call):
                continue

            # Check if this is an ORM constructor call
            func_name = _get_qualified_name(node.func)
            if func_name is None:
                continue

            # Check for **model_dump() or **dict() patterns
            has_mass_assignment = False
            dump_source = ""
            for kw in node.keywords:
                if _is_unpacking_dict(kw):
                    has_mass_assignment = True
                    # Try to identify the source
                    if isinstance(kw.value, ast.Call):
                        if isinstance(kw.value.func, ast.Attribute):
                            dump_source = _get_qualified_name(kw.value.func.value) or ""
                        elif isinstance(kw.value.func, ast.Name):
                            dump_source = kw.value.func.id
                    break

            if not has_mass_assignment:
                continue

            # Check if the constructor looks like an ORM model
            class_name = func_name
            if "." in class_name:
                class_name = class_name.rsplit(".", 1)[-1]

            # Heuristic: class names that look like ORM models
            looks_like_orm = (
                class_name[0].isupper()  # PascalCase
                and not class_name.endswith(("Schema", "Mixin", "Config", "Type", "Enum"))
                and not class_name in ("dict", "Dict", "list", "List", "set", "Set", "str", "int", "float", "bool")
            )

            if not looks_like_orm:
                continue

            # Check if there's also an explicit exclude/unset filtering
            has_exclude = False
            for kw in node.keywords:
                if kw.arg is not None:
                    continue
                if not isinstance(kw.value, ast.Call):
                    continue
                # Check for model_dump(exclude=...) or dict(exclude_unset=True)
                for inner_kw in kw.value.keywords:
                    if inner_kw.arg in ("exclude", "exclude_unset", "exclude_defaults", "include"):
                        has_exclude = True
                        break

            if has_exclude:
                continue

            dump_desc = f"{dump_source}.model_dump()" if dump_source else "dict()"
            message = (
                f"Potential mass assignment: `{func_name}(**{dump_desc})` "
                f"may allow setting sensitive fields (is_superuser, is_active, role, etc.). "
                f"Use `model_dump(exclude=...)` or a dedicated Create schema."
            )

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=message,
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
                        title="Use explicit field mapping or exclude sensitive fields",
                        replacement=(
                            f"{func_name}(\n"
                            f"    **{dump_source}.model_dump(exclude={{'is_superuser', 'is_active', 'role'}}),\n"
                            f"    # Or better: use a dedicated Create schema\n"
                            f")"
                        ),
                        explanation=(
                            "Mass assignment occurs when user input is passed directly to ORM "
                            "constructors. An attacker can add fields like `is_superuser=true` "
                            "to their request payload. Use Pydantic Create schemas that explicitly "
                            "exclude sensitive fields, or use `model_dump(exclude=...)` to filter them."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
