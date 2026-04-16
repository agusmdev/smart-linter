"""Tests for SEC004: Unauthenticated mutation endpoints."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.unauthenticated_mutation import UnauthenticatedMutationRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = UnauthenticatedMutationRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_post_without_auth() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        async def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 1
    assert "Unauthenticated" in messages[0]
    assert "create_item" in messages[0]


def test_detects_delete_without_auth() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.delete("/items/{id}")
        def delete_item(id: int):
            pass
    """)
    assert len(messages) == 1
    assert "delete_item" in messages[0]


def test_detects_put_without_auth() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.put("/items/{id}")
        def update_item(id: int, item: ItemUpdate):
            pass
    """)
    assert len(messages) == 1


def test_detects_patch_without_auth() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.patch("/items/{id}")
        def patch_item(id: int):
            pass
    """)
    assert len(messages) == 1


def test_passes_with_current_user_param() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        async def create_item(item: ItemCreate, current_user: CurrentUser):
            return item
    """)
    assert len(messages) == 0


def test_passes_with_depends_auth_in_decorator() -> None:
    messages = _check("""
        from fastapi import APIRouter, Depends
        router = APIRouter()

        @router.post("/items", dependencies=[Depends(get_current_user)])
        async def create_item(item: ItemCreate):
            return item
    """)
    assert len(messages) == 0


def test_passes_with_depends_get_current_superuser() -> None:
    messages = _check("""
        from fastapi import APIRouter, Depends
        router = APIRouter()

        @router.delete("/users/{id}", dependencies=[Depends(get_current_superuser)])
        def delete_user(id: int):
            pass
    """)
    assert len(messages) == 0


def test_passes_with_token_param() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/items")
        async def create_item(item: ItemCreate, token: str = Depends(oauth2_scheme)):
            return item
    """)
    assert len(messages) == 0


def test_passes_login_endpoint() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/login/access-token")
        def login(form_data: OAuth2PasswordRequestForm = Depends()):
            return {"token": "abc"}
    """)
    assert len(messages) == 0


def test_passes_register_endpoint() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/users/signup")
        def register_user(user_in: UserRegister):
            return user_in
    """)
    assert len(messages) == 0


def test_passes_password_reset() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/reset-password/")
        def reset_password(body: NewPassword):
            return {"message": "ok"}
    """)
    assert len(messages) == 0


def test_passes_webhook_endpoint() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.post("/webhooks/stripe")
        async def stripe_webhook(payload: dict):
            return {"status": "ok"}
    """)
    assert len(messages) == 0


def test_skips_get_endpoints() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/items")
        def read_items():
            return []
    """)
    assert len(messages) == 0


def test_passes_with_api_key_auth() -> None:
    messages = _check("""
        from fastapi import APIRouter, Depends
        router = APIRouter()

        @router.post("/items")
        async def create_item(item: ItemCreate, api_key: str = Depends(get_api_key)):
            return item
    """)
    assert len(messages) == 0


def test_passes_with_get_current_active_superuser() -> None:
    """Test the exact pattern from fastapi-benchmark users.py."""
    messages = _check("""
        from fastapi import APIRouter, Depends
        router = APIRouter(prefix="/users")

        @router.post(
            "/", dependencies=[Depends(get_current_active_superuser)], response_model=UserPublic
        )
        def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
            pass
    """)
    assert len(messages) == 0


def test_real_world_private_endpoint() -> None:
    """Test from fastapi-benchmark private.py - create_user with no auth."""
    messages = _check("""
        from fastapi import APIRouter
        from pydantic import BaseModel

        router = APIRouter(tags=["private"], prefix="/private")

        class PrivateUserCreate(BaseModel):
            email: str
            password: str
            full_name: str

        @router.post("/users/", response_model=UserPublic)
        def create_user(user_in: PrivateUserCreate, session: SessionDep) -> Any:
            user = User(email=user_in.email, hashed_password=get_password_hash(user_in.password))
            session.add(user)
            session.commit()
            return user
    """)
    assert len(messages) == 1
    assert "create_user" in messages[0]


def test_real_world_boilerplate_write_user() -> None:
    """Test from fastapi-boiler - POST /user without auth (signup)."""
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter(tags=["users"])

        @router.post("/user", response_model=UserRead, status_code=201)
        async def write_user(request: Request, user: UserCreate, db: Annotated[AsyncSession, Depends(async_get_db)]):
            created_user = await crud_users.create(db=db, object=user_internal, schema_to_select=UserRead)
            return created_user
    """)
    # write_user with POST /user and no auth dependency - this IS flagged
    # but it's a signup endpoint so it should be considered...
    # Actually "write_user" doesn't match any public pattern, and "/user" doesn't have public segments
    assert len(messages) == 1
