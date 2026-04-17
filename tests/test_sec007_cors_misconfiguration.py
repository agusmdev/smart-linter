"""Tests for SEC007: CORS misconfiguration."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.cors_misconfiguration import CorsMisconfigurationRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = CorsMisconfigurationRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_wildcard_with_credentials() -> None:
    messages = _check("""
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    """)
    assert len(messages) == 1
    assert "allow_origins" in messages[0]
    assert "allow_credentials" in messages[0]


def test_passes_specific_origins_with_credentials() -> None:
    messages = _check("""
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://example.com"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    """)
    assert len(messages) == 0


def test_passes_wildcard_without_credentials() -> None:
    messages = _check("""
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
        )
    """)
    assert len(messages) == 0


def test_passes_wildcard_no_credentials_kwarg() -> None:
    messages = _check("""
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
        )
    """)
    assert len(messages) == 0


def test_passes_multiple_origins_with_credentials() -> None:
    messages = _check("""
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://a.com", "https://b.com"],
            allow_credentials=True,
        )
    """)
    assert len(messages) == 0


def test_passes_non_cors_middleware() -> None:
    messages = _check("""
        app.add_middleware(
            SomeMiddleware,
            origins=["*"],
            credentials=True,
        )
    """)
    assert len(messages) == 0
