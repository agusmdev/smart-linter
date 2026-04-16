"""Tests for ASYNC003: Async function without await."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.async_no_await import AsyncNoAwaitRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = AsyncNoAwaitRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_async_without_await() -> None:
    messages = _check("""
        async def process():
            return 42
    """)
    assert len(messages) == 1
    assert "process" in messages[0]
    assert "regular `def`" in messages[0]


def test_passes_async_with_await() -> None:
    messages = _check("""
        async def fetch_data():
            result = await db.query()
            return result
    """)
    assert len(messages) == 0


def test_passes_async_with_async_for() -> None:
    messages = _check("""
        async def iterate():
            async for item in stream:
                print(item)
    """)
    assert len(messages) == 0


def test_passes_async_with_async_with() -> None:
    messages = _check("""
        async def read_file():
            async with aiofiles.open("f.txt") as f:
                return await f.read()
    """)
    assert len(messages) == 0


def test_detects_fastapi_endpoint_without_await() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/health")
        async def health_check():
            return {"status": "ok"}
    """)
    assert len(messages) == 1
    assert "FastAPI" in messages[0]


def test_passes_fastapi_endpoint_with_await() -> None:
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/users")
        async def get_users(db: SessionDep):
            users = await db.execute(select(User))
            return users.all()
    """)
    assert len(messages) == 0


def test_passes_dunder_methods() -> None:
    messages = _check("""
        class MyContext:
            async def __aenter__(self):
                return self
    """)
    assert len(messages) == 0


def test_passes_test_functions() -> None:
    messages = _check("""
        async def test_something():
            assert 1 == 1
    """)
    assert len(messages) == 0


def test_passes_nested_async_def() -> None:
    """Parent async function that defines a nested async function should be OK."""
    messages = _check("""
        async def setup():
            async def inner():
                await something()
            return inner
    """)
    assert len(messages) == 0


def test_detects_async_with_sync_work() -> None:
    """Real-world pattern: async health check that does no async I/O."""
    messages = _check("""
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/health")
        async def health():
            return {"status": "healthy", "version": "1.0"}
    """)
    assert len(messages) == 1


def test_real_world_health_endpoint() -> None:
    """Pattern from fastapi-boiler health.py."""
    messages = _check("""
        from fastapi import APIRouter, status
        from fastapi.responses import JSONResponse

        router = APIRouter(tags=["health"])

        @router.get("/health", response_model=HealthCheck)
        async def health():
            http_status = status.HTTP_200_OK
            response = {
                "status": "healthy",
                "version": settings.APP_VERSION,
            }
            return JSONResponse(status_code=http_status, content=response)
    """)
    assert len(messages) == 1
    assert "health" in messages[0]


def test_passes_regular_def() -> None:
    messages = _check("""
        def process():
            return 42
    """)
    assert len(messages) == 0


def test_detects_multiple_async_without_await() -> None:
    messages = _check("""
        async def func1():
            return 1

        async def func2():
            x = compute()
            return x

        async def func3():
            await something()
    """)
    assert len(messages) == 2
