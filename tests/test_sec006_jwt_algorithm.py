"""Tests for SEC006: JWT decode without algorithm specification."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.jwt_algorithm import JwtAlgorithmRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = JwtAlgorithmRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_jwt_decode_without_algorithms() -> None:
    messages = _check("""
        import jwt
        payload = jwt.decode(token, SECRET_KEY)
    """)
    assert len(messages) == 1
    assert "algorithms" in messages[0]
    assert "algorithm confusion" in messages[0]


def test_passes_jwt_decode_with_algorithms() -> None:
    messages = _check("""
        import jwt
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    """)
    assert len(messages) == 0


def test_passes_jwt_decode_with_kwarg_algorithms() -> None:
    messages = _check("""
        import jwt
        payload = jwt.decode(token, key=SECRET_KEY, algorithms=["HS256"])
    """)
    assert len(messages) == 0


def test_detects_no_algorithms_multiple_args() -> None:
    messages = _check("""
        import jwt
        payload = jwt.decode(token, SECRET_KEY, options={"verify_exp": True})
    """)
    assert len(messages) == 1


def test_passes_non_jwt_decode() -> None:
    messages = _check("""
        import base64
        data = base64.decode(payload)
    """)
    assert len(messages) == 0


def test_detects_jose_jwt_decode() -> None:
    messages = _check("""
        from jose import jwt
        payload = jwt.decode(token, SECRET_KEY)
    """)
    assert len(messages) == 1


def test_passes_jose_with_algorithms() -> None:
    messages = _check("""
        from jose import jwt
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    """)
    assert len(messages) == 0


def test_real_world_correct_usage() -> None:
    """Pattern from fastapi-benchmark and fastapi-boiler."""
    messages = _check("""
        import jwt
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        token_data = TokenPayload(**payload)
    """)
    assert len(messages) == 0


def test_real_world_vulnerable_usage() -> None:
    messages = _check("""
        import jwt
        payload = jwt.decode(token, SECRET_KEY)
        user_id = payload.get("sub")
    """)
    assert len(messages) == 1
