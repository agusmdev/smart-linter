"""Tests for SEC005: Mass assignment via **model_dump() in ORM constructors."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.mass_assignment import MassAssignmentRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = MassAssignmentRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_model_dump_in_orm_constructor() -> None:
    messages = _check("""
        user = User(**user_in.model_dump())
    """)
    assert len(messages) == 1
    assert "mass assignment" in messages[0].lower()
    assert "User" in messages[0]


def test_detects_dict_in_orm_constructor() -> None:
    messages = _check("""
        item = Item(**data.dict())
    """)
    assert len(messages) == 1


def test_detects_asdict_in_constructor() -> None:
    messages = _check("""
        record = Record(**asdict(item))
    """)
    assert len(messages) == 1


def test_passes_with_exclude() -> None:
    messages = _check("""
        user = User(**user_in.model_dump(exclude={"is_superuser", "is_active"}))
    """)
    assert len(messages) == 0


def test_passes_with_exclude_unset() -> None:
    messages = _check("""
        user = User(**user_in.model_dump(exclude_unset=True))
    """)
    assert len(messages) == 0


def test_passes_dict_literal() -> None:
    messages = _check("""
        user = User(name="Alice", email="alice@example.com")
    """)
    assert len(messages) == 0


def test_passes_non_orm_constructor() -> None:
    messages = _check("""
        config = dict(**settings.model_dump())
    """)
    assert len(messages) == 0


def test_passes_schema_class() -> None:
    messages = _check("""
        result = UserSchema(**user.model_dump())
    """)
    # UserSchema ends with Schema, should not be flagged
    assert len(messages) == 0


def test_real_world_dispatch_pattern() -> None:
    """Pattern from Netflix Dispatch: CaseCostType(**case_cost_type_in.dict())."""
    messages = _check("""
        case_cost_type = CaseCostType(**case_cost_type_in.dict(exclude={"project"}), project=project)
    """)
    # This has exclude, so it should NOT be flagged
    assert len(messages) == 0


def test_real_world_vulnerable_pattern() -> None:
    messages = _check("""
        user = User(**user_create.model_dump())
        db.add(user)
        db.commit()
    """)
    assert len(messages) == 1
    assert "User" in messages[0]


def test_passes_sqlmodel_validate() -> None:
    messages = _check("""
        item = Item.model_validate(item_in, update={"owner_id": current_user.id})
    """)
    assert len(messages) == 0
