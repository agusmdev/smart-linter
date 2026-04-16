"""Tests for RESP001: Missing response_model on API endpoints."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.missing_response_model import MissingResponseModelRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = MissingResponseModelRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_post_without_response_model() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        async def create_item(item: ItemCreate) -> ItemPublic:
            return item
    """)
    assert len(messages) == 1
    assert "response_model" in messages[0]
    assert "create_item" in messages[0]


def test_detects_delete_without_response_model() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.delete("/items/{id}")
        def delete_item(id: int):
            session.delete(item)
            session.commit()
            return {"message": "deleted"}
    """)
    assert len(messages) == 1


def test_detects_patch_without_response_model() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.patch("/items/{id}")
        def patch_item(id: int, values: ItemUpdate) -> dict[str, str]:
            return {"message": "updated"}
    """)
    # dict return type — should NOT flag (primitive-like)
    assert len(messages) == 0


def test_detects_get_without_response_model_complex_return() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/items/{id}")
        def read_item(id: int) -> ItemPublic:
            return session.get(Item, id)
    """)
    assert len(messages) == 1


def test_passes_with_response_model() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items", response_model=ItemPublic)
        async def create_item(item: ItemCreate) -> Any:
            return item
    """)
    assert len(messages) == 0


def test_passes_with_response_class() -> None:
    messages = _check("""
        from fastapi import APIRouter
        from fastapi.responses import HTMLResponse
        router = APIRouter()

        @router.get("/page", response_class=HTMLResponse)
        async def get_page() -> str:
            return "<html>...</html>"
    """)
    assert len(messages) == 0


def test_passes_bool_return() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/health")
        async def health_check() -> bool:
            return True
    """)
    assert len(messages) == 0


def test_passes_dict_return() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        def create_item(item: ItemCreate) -> dict[str, str]:
            return {"message": "created"}
    """)
    assert len(messages) == 0


def test_passes_health_endpoint() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/health-check/")
        async def health_check():
            return True
    """)
    assert len(messages) == 0


def test_detects_no_annotation_no_response_model() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        async def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 1
    assert "no return type annotation" in messages[0]


def test_passes_redirect_response() -> None:
    messages = _check("""
        from fastapi import APIRouter
        from fastapi.responses import RedirectResponse
        router = APIRouter()

        @router.get("/old-url")
        async def redirect_to_new() -> RedirectResponse:
            return RedirectResponse(url="/new-url")
    """)
    assert len(messages) == 0


def test_real_world_delete_without_response_model() -> None:
    """Pattern from fastapi-benchmark items.py:delete_item."""
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter(prefix="/items")

        @router.delete("/{id}")
        def delete_item(session: SessionDep, current_user: CurrentUser, id: uuid.UUID) -> Message:
            session.delete(item)
            session.commit()
            return Message(message="Item deleted successfully")
    """)
    assert len(messages) == 1
    assert "delete_item" in messages[0]


def test_real_world_users_boilerplate() -> None:
    """Pattern from fastapi-boiler users.py:patch_user."""
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter(tags=["users"])

        @router.patch("/user/{username}")
        async def patch_user(request: Request, values: UserUpdate, username: str,
                             current_user: Annotated[dict, Depends(get_current_user)],
                             db: Annotated[AsyncSession, Depends(async_get_db)]) -> dict[str, str]:
            await crud_users.update(db=db, object=values, username=username)
            return {"message": "User updated"}
    """)
    # dict[str, str] return type — should NOT flag
    assert len(messages) == 0
