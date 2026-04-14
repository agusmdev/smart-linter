"""ASYNC001: Detect sync blocking calls inside async FastAPI endpoints."""

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

HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "options", "head"})

BLOCKING_CALLS: dict[str, tuple[str, str]] = {
    "requests.get": ("httpx.AsyncClient", "await async_client.get(...)"),
    "requests.post": ("httpx.AsyncClient", "await async_client.post(...)"),
    "requests.put": ("httpx.AsyncClient", "await async_client.put(...)"),
    "requests.delete": ("httpx.AsyncClient", "await async_client.delete(...)"),
    "requests.patch": ("httpx.AsyncClient", "await async_client.patch(...)"),
    "requests.head": ("httpx.AsyncClient", "await async_client.head(...)"),
    "requests.options": ("httpx.AsyncClient", "await async_client.options(...)"),
    "requests.request": ("httpx.AsyncClient", "await async_client.request(...)"),
    "httpx.get": (
        "httpx.AsyncClient",
        "async with httpx.AsyncClient() as client: await client.get(...)",
    ),
    "httpx.post": (
        "httpx.AsyncClient",
        "async with httpx.AsyncClient() as client: await client.post(...)",
    ),
    "httpx.put": (
        "httpx.AsyncClient",
        "async with httpx.AsyncClient() as client: await client.put(...)",
    ),
    "httpx.delete": (
        "httpx.AsyncClient",
        "async with httpx.AsyncClient() as client: await client.delete(...)",
    ),
    "httpx.request": (
        "httpx.AsyncClient",
        "async with httpx.AsyncClient() as client: await client.request(...)",
    ),
    "time.sleep": ("asyncio.sleep", "await asyncio.sleep(...)"),
    "subprocess.run": (
        "asyncio.create_subprocess_exec",
        "proc = await asyncio.create_subprocess_exec(...)",
    ),
    "subprocess.call": (
        "asyncio.create_subprocess_exec",
        "proc = await asyncio.create_subprocess_exec(...)",
    ),
    "subprocess.check_output": (
        "asyncio.create_subprocess_exec",
        "proc = await asyncio.create_subprocess_exec(...)",
    ),
    "subprocess.check_call": (
        "asyncio.create_subprocess_exec",
        "proc = await asyncio.create_subprocess_exec(...)",
    ),
    "subprocess.Popen": (
        "asyncio.create_subprocess_exec",
        "proc = await asyncio.create_subprocess_exec(...)",
    ),
    "os.system": (
        "asyncio.create_subprocess_shell",
        "proc = await asyncio.create_subprocess_shell(...)",
    ),
    "os.popen": (
        "asyncio.create_subprocess_shell",
        "proc = await asyncio.create_subprocess_shell(...)",
    ),
    "input": ("asyncio.to_thread", "await asyncio.to_thread(input, ...)"),
    "open": (
        "aiofiles.open / anyio.open_file",
        "async with aiofiles.open(...) as f: ...",
    ),
}

BLOCKING_ATTRS: dict[str, set[str]] = {
    "requests": HTTP_METHODS | {"request"},
    "httpx": HTTP_METHODS | {"request"},
    "subprocess": {
        "run",
        "call",
        "check_output",
        "check_call",
        "Popen",
        "getoutput",
        "getstatusoutput",
    },
}

BLOCKING_BARE_CALLS = frozenset({"input", "open"})

OS_PATH_FUNCS = frozenset(
    {
        "exists",
        "isdir",
        "isfile",
        "getsize",
        "getmtime",
        "getatime",
        "getctime",
        "islink",
        "lexists",
        "getcwdu",
    }
)

PATHLIB_BLOCKING_METHODS = frozenset(
    {
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "mkdir",
        "rmdir",
        "unlink",
        "rename",
        "replace",
        "glob",
        "rglob",
        "iterdir",
    }
)

SAFE_WRAPPER_PREFIXES = (
    "asyncio.to_thread",
    "asyncio.ensure_future",
    "loop.run_in_executor",
    "anyio.to_thread.run_sync",
    "anyio.open_file",
    "trio.to_thread.run_sync",
    "run_in_threadpool",
)

SAFE_WRAPPER_ATTRS = frozenset(
    {"to_thread", "run_in_executor", "run_sync", "run_in_threadpool", "open_file"}
)


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


def _is_fastapi_route_decorator(decorator: ast.expr) -> bool:
    if isinstance(decorator, ast.Call):
        func = decorator.func
    elif isinstance(decorator, ast.Attribute):
        func = decorator
    else:
        return False

    if isinstance(func, ast.Attribute):
        return func.attr in HTTP_METHODS or func.attr == "api_route"

    return False


def _is_in_safe_wrapper(
    call_node: ast.Call, parent_map: dict[ast.AST, ast.AST]
) -> bool:
    parent = parent_map.get(call_node)
    while parent is not None:
        if isinstance(parent, ast.Call):
            func = parent.func
            func_name = _get_qualified_name(func)
            if func_name and any(
                func_name.startswith(p) for p in SAFE_WRAPPER_PREFIXES
            ):
                return True
            if isinstance(func, ast.Attribute) and func.attr in SAFE_WRAPPER_ATTRS:
                return True
        parent = parent_map.get(parent)
    return False


def _get_qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value:
            return f"{value}.{node.attr}"
    return None


def _is_awaited(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> bool:
    parent = parent_map.get(node)
    if isinstance(parent, ast.Await):
        return True
    if isinstance(parent, (ast.AsyncWith, ast.AsyncFor)):
        return True
    return False


def _is_wrapped_in_anyio_open_file(
    call: ast.Call, parent_map: dict[ast.AST, ast.AST]
) -> bool:
    parent = parent_map.get(call)
    while parent is not None:
        if isinstance(parent, ast.Call):
            func_name = _get_qualified_name(parent.func)
            if func_name and func_name.startswith("anyio.open_file"):
                return True
            if func_name and func_name.startswith("aiofiles.open"):
                return True
        parent = parent_map.get(parent)
    return False


def _get_blocking_call_name(
    call: ast.Call, parent_map: dict[ast.AST, ast.AST]
) -> str | None:
    if isinstance(call.func, ast.Attribute):
        value_name = _get_qualified_name(call.func.value)
        attr = call.func.attr

        if value_name and value_name in BLOCKING_ATTRS:
            if attr in BLOCKING_ATTRS[value_name]:
                return f"{value_name}.{attr}"

        if value_name == "os.path" and attr in OS_PATH_FUNCS:
            return f"os.path.{attr}"

        qualified = _get_qualified_name(call.func)
        if qualified and qualified in BLOCKING_CALLS:
            return qualified

        if attr in PATHLIB_BLOCKING_METHODS:
            if isinstance(call.func.value, ast.Call):
                inner_name = _get_qualified_name(call.func.value.func)
                if inner_name in ("pathlib.Path", "Path"):
                    return f"Path(...).{attr}"
            elif value_name in ("pathlib.Path", "Path"):
                return f"Path(...).{attr}"

    if isinstance(call.func, ast.Name):
        if call.func.id == "open":
            if not _is_wrapped_in_anyio_open_file(call, parent_map):
                return "open"

        if call.func.id in BLOCKING_BARE_CALLS:
            return call.func.id

        qualified = call.func.id
        if qualified in BLOCKING_CALLS:
            return qualified

    return None


class AsyncSyncRule(Rule):
    id: ClassVar[str] = "ASYNC001"
    description: ClassVar[str] = (
        "Sync blocking call detected inside async FastAPI endpoint"
    )
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("async", "fastapi", "performance")

    def check(self, tree, filename: str = "") -> list[Violation]:
        parent_map = _build_parent_map(tree)
        violations: list[Violation] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            if not any(_is_fastapi_route_decorator(d) for d in node.decorator_list):
                continue

            self._check_async_body(node, parent_map, filename, violations)

        return violations

    def _check_async_body(
        self,
        func: ast.AsyncFunctionDef,
        parent_map: dict[ast.AST, ast.AST],
        filename: str,
        violations: list[Violation],
    ) -> None:
        for child in ast.walk(func):
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child is not func
            ):
                continue

            if not isinstance(child, ast.Call):
                continue

            if _is_awaited(child, parent_map):
                continue

            if _is_in_safe_wrapper(child, parent_map):
                continue

            call_name = _get_blocking_call_name(child, parent_map)
            if call_name is None:
                continue

            fix = self._build_fix(call_name)

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=f"Blocking sync call `{call_name}()` in async FastAPI endpoint `{func.name}`",
                    location=Location(row=child.lineno, column=child.col_offset + 1),
                    end_location=Location(
                        row=child.end_lineno or child.lineno,
                        column=(child.end_col_offset or child.col_offset) + 1,
                    ),
                    severity=self.severity,
                    fix=fix,
                    filename=filename,
                )
            )

    def _build_fix(self, call_name: str) -> FixSuggestion | None:
        if call_name in BLOCKING_CALLS:
            replacement, example = BLOCKING_CALLS[call_name]
            return FixSuggestion(
                title=f"Replace `{call_name}()` with async alternative",
                replacement=example,
                explanation=f"Use `{replacement}` instead. "
                "Blocking calls in async endpoints stall the event loop and degrade concurrency.",
            )
        if call_name.startswith("Path(...)."):
            method = call_name.split(".")[-1]
            return FixSuggestion(
                title=f"Replace `Path(...).{method}()` with async alternative",
                replacement=f"await anyio.Path(...).{method}()",
                explanation="Use `anyio.Path` (or `aiofiles.os`) instead. "
                "`pathlib.Path` methods perform blocking file I/O.",
            )
        return FixSuggestion(
            title=f"Wrap `{call_name}()` in `asyncio.to_thread()`",
            replacement=f"await asyncio.to_thread({call_name}, ...)",
            explanation="Blocking calls in async endpoints stall the event loop. "
            "Either use an async alternative or wrap in `asyncio.to_thread()`.",
        )
