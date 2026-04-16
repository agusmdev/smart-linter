"""Tests for FAST001: BaseHTTPMiddleware usage detection."""

from __future__ import annotations

import ast
import textwrap

from smart_linter.rules.basehttp_middleware import BaseHTTPMiddlewareRule


def _check(source: str, filename: str = "test.py") -> list[str]:
    tree = ast.parse(textwrap.dedent(source))
    rule = BaseHTTPMiddlewareRule()
    violations = rule.check(tree, filename=filename)
    return [v.message for v in violations]


def test_detects_basehttp_middleware() -> None:
    messages = _check("""
        from starlette.middleware.base import BaseHTTPMiddleware

        class MyMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                return response
    """)
    assert len(messages) == 1
    assert "MyMiddleware" in messages[0]
    assert "BaseHTTPMiddleware" in messages[0]


def test_detects_with_fastapi_import() -> None:
    messages = _check("""
        from fastapi import FastAPI
        from starlette.middleware.base import BaseHTTPMiddleware

        class LoggerMiddleware(BaseHTTPMiddleware):
            def __init__(self, app: FastAPI):
                super().__init__(app)

            async def dispatch(self, request, call_next):
                response = await call_next(request)
                return response
    """)
    assert len(messages) == 1


def test_passes_pure_asgi_middleware() -> None:
    messages = _check("""
        class PureASGIMiddleware:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                await self.app(scope, receive, send)
    """)
    assert len(messages) == 0


def test_passes_unrelated_class() -> None:
    messages = _check("""
        class MyService:
            def process(self):
                pass
    """)
    assert len(messages) == 0


def test_passes_other_middleware() -> None:
    messages = _check("""
        from starlette.middleware.cors import CORSMiddleware

        class MyCORSMiddleware(CORSMiddleware):
            pass
    """)
    assert len(messages) == 0


def test_real_world_logger_middleware() -> None:
    """Pattern from fastapi-boiler."""
    messages = _check("""
        from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
        from starlette.responses import Response

        class LoggerMiddleware(BaseHTTPMiddleware):
            def __init__(self, app):
                super().__init__(app)

            async def dispatch(self, request, call_next):
                request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                return response
    """)
    assert len(messages) == 1
    assert "LoggerMiddleware" in messages[0]


def test_multiple_middleware_classes() -> None:
    messages = _check("""
        from starlette.middleware.base import BaseHTTPMiddleware

        class FirstMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                return await call_next(request)

        class SecondMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                return await call_next(request)
    """)
    assert len(messages) == 2
