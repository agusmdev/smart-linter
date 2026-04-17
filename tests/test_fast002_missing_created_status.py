"""Tests for FAST002: POST creation endpoints without status_code=201."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.missing_created_status import MissingCreatedStatusRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = MissingCreatedStatusRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_create_post_without_status() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 1
    assert "201" in messages[0]
    assert "create_item" in messages[0]


def test_detects_add_post_without_status() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/tags")
        def add_tag(tag: TagCreate):
            return tag
    """)
    assert len(messages) == 1


def test_passes_with_status_201() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items", status_code=201)
        def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 0


def test_passes_with_http_201_created() -> None:
    messages = _check("""
        from fastapi import APIRouter, status
        router = APIRouter()

        @router.post("/items", status_code=status.HTTP_201_CREATED)
        def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 0


def test_passes_with_any_explicit_status() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items", status_code=202)
        def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 0


def test_passes_non_create_post() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items/search")
        def search_items(query: SearchQuery):
            return []
    """)
    assert len(messages) == 0


def test_passes_login_endpoint() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/login")
        def login(form_data: OAuth2PasswordRequestForm = Depends()):
            return {"token": "abc"}
    """)
    assert len(messages) == 0


def test_passes_get_endpoints() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/items")
        def get_items():
            return []
    """)
    assert len(messages) == 0


def test_detects_write_post() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/user")
        async def write_user(request: Request, user: UserCreate):
            return created_user
    """)
    assert len(messages) == 1


def test_detects_register_post() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/register")
        async def register_user(user_in: UserRegister):
            return user
    """)
    assert len(messages) == 1


def test_detects_save_post() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/drafts")
        def save_draft(draft: DraftCreate):
            return draft
    """)
    assert len(messages) == 1
