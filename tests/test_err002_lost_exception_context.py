"""Tests for ERR002: Lost exception context in except blocks."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.ast_utils import build_parent_map
from smart_linter.rules.lost_exception_context import LostExceptionContextRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    parent_map = build_parent_map(tree)
    rule = LostExceptionContextRule()
    rule._parent_map = parent_map
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_raise_without_from() -> None:
    messages = _check("""
        try:
            do_something()
        except ValueError as e:
            raise RuntimeError("Failed")
    """)
    assert len(messages) == 1
    assert "from" in messages[0]
    assert "context is lost" in messages[0]


def test_detects_raise_custom_without_from() -> None:
    messages = _check("""
        try:
            parse_data()
        except json.JSONDecodeError as e:
            raise DataError("Invalid data")
    """)
    assert len(messages) == 1


def test_passes_with_from_e() -> None:
    messages = _check("""
        try:
            do_something()
        except ValueError as e:
            raise RuntimeError("Failed") from e
    """)
    assert len(messages) == 0


def test_passes_with_from_none() -> None:
    messages = _check("""
        try:
            do_something()
        except ValueError as e:
            raise RuntimeError("Failed") from None
    """)
    assert len(messages) == 0


def test_passes_bare_reraise() -> None:
    messages = _check("""
        try:
            do_something()
        except ValueError:
            raise
    """)
    assert len(messages) == 0


def test_passes_reraise_same_exception() -> None:
    messages = _check("""
        try:
            do_something()
        except ValueError as e:
            raise e
    """)
    assert len(messages) == 0


def test_passes_http_exception() -> None:
    """HTTPException is acceptable to raise without from in web context."""
    messages = _check("""
        try:
            result = parse_token(token)
        except InvalidTokenError:
            raise HTTPException(status_code=403, detail="Invalid credentials")
    """)
    assert len(messages) == 0


def test_passes_not_implemented_error() -> None:
    messages = _check("""
        try:
            result = old_api()
        except DeprecationWarning:
            raise NotImplementedError("Use new_api instead")
    """)
    assert len(messages) == 0


def test_passes_exception_passed_as_arg() -> None:
    messages = _check("""
        try:
            process()
        except ValueError as e:
            raise CustomError(str(e))
    """)
    assert len(messages) == 0


def test_passes_exception_in_fstring() -> None:
    messages = _check("""
        try:
            process()
        except ValueError as e:
            raise CustomError(f"Failed: {e}")
    """)
    assert len(messages) == 0


def test_detects_nested_except() -> None:
    messages = _check("""
        try:
            try:
                do_something()
            except ValueError as e:
                raise RuntimeError("Inner failed")
        except Exception as outer:
            pass
    """)
    assert len(messages) == 1
    assert "RuntimeError" in messages[0]


def test_passes_raise_outside_except() -> None:
    messages = _check("""
        if not valid:
            raise ValueError("Invalid")
    """)
    assert len(messages) == 0


def test_detects_bare_except() -> None:
    messages = _check("""
        try:
            do_something()
        except:
            raise RuntimeError("Something went wrong")
    """)
    assert len(messages) == 1


def test_real_world_jwt_decode() -> None:
    """Pattern from fastapi-benchmark deps.py."""
    messages = _check("""
        try:
            payload = jwt.decode(token, key, algorithms=["HS256"])
            token_data = TokenPayload(**payload)
        except (InvalidTokenError, ValidationError):
            raise HTTPException(status_code=403, detail="Could not validate credentials")
    """)
    # HTTPException is in acceptable list
    assert len(messages) == 0


def test_real_world_db_query() -> None:
    """Common pattern: catch DB error and raise domain error."""
    messages = _check("""
        try:
            user = db.query(User).filter(User.id == user_id).one()
        except NoResultFound as e:
            raise NotFoundError(f"User {user_id} not found")
    """)
    assert len(messages) == 1
    assert "from" in messages[0]
