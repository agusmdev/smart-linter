"""ASYNC001: Detect sync blocking calls inside async FastAPI endpoints."""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.ast_utils import (
    build_parent_map as _build_parent_map,
)
from smart_linter.ast_utils import (
    get_qualified_name as _get_qualified_name,
)
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

BLOCKING_ATTRS: dict[str, frozenset[str]] = {
    "requests": HTTP_METHODS | {"request"},
    "httpx": HTTP_METHODS | {"request"},
    "subprocess": frozenset(
        {
            "run",
            "call",
            "check_output",
            "check_call",
            "Popen",
            "getoutput",
            "getstatusoutput",
        }
    ),
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

SAFE_WRAPPER_ATTRS = frozenset({"to_thread", "run_in_executor", "run_sync", "run_in_threadpool", "open_file"})


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


def _is_in_safe_wrapper(call_node: ast.Call, parent_map: dict[ast.AST, ast.AST]) -> bool:
    parent = parent_map.get(call_node)
    while parent is not None:
        if isinstance(parent, ast.Call):
            func = parent.func
            func_name = _get_qualified_name(func)
            if func_name and any(func_name.startswith(p) for p in SAFE_WRAPPER_PREFIXES):
                return True
            if isinstance(func, ast.Attribute) and func.attr in SAFE_WRAPPER_ATTRS:
                return True
        parent = parent_map.get(parent)
    return False


def _is_awaited(node: ast.AST, parent_map: dict[ast.AST, ast.AST]) -> bool:
    parent = parent_map.get(node)
    if isinstance(parent, ast.Await):
        return True
    return bool(isinstance(parent, (ast.AsyncWith, ast.AsyncFor)))


def _is_wrapped_in_anyio_open_file(call: ast.Call, parent_map: dict[ast.AST, ast.AST]) -> bool:
    parent = parent_map.get(call)
    while parent is not None:
        if isinstance(parent, ast.Call):
            func_name = _get_qualified_name(parent.func)
            if func_name and func_name.startswith("anyio.open_file"):
                return True  # pragma: no cover
            if func_name and func_name.startswith("aiofiles.open"):
                return True
        parent = parent_map.get(parent)
    return False


def _get_blocking_call_name(call: ast.Call, parent_map: dict[ast.AST, ast.AST]) -> str | None:
    if isinstance(call.func, ast.Attribute):
        value_name = _get_qualified_name(call.func.value)
        attr = call.func.attr

        if value_name and value_name in BLOCKING_ATTRS and attr in BLOCKING_ATTRS[value_name]:
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
        if call.func.id in BLOCKING_BARE_CALLS:
            if call.func.id == "open" and _is_wrapped_in_anyio_open_file(call, parent_map):
                return None
            return call.func.id

        qualified = call.func.id
        if qualified in BLOCKING_CALLS:  # pragma: no cover
            return qualified

    return None


TRANSITIVE_DEPTH_LIMIT = 5


def _build_function_index(
    tree: ast.AST,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index[node.name] = node
    return index


def _resolve_call_target(
    call: ast.Call,
    func_index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    if isinstance(call.func, ast.Name):
        target = func_index.get(call.func.id)
        if target is not None and target is not call:
            return target
    return None


def _extract_depends_targets(
    func: ast.AsyncFunctionDef,
) -> list[str]:
    targets: list[str] = []
    for default in func.args.defaults:
        if (
            isinstance(default, ast.Call)
            and isinstance(default.func, ast.Name)
            and default.func.id == "Depends"
            and default.args
            and isinstance(default.args[0], ast.Name)
        ):
            targets.append(default.args[0].id)
    return targets


def _find_transitive_blocking(
    func_body: ast.FunctionDef | ast.AsyncFunctionDef,
    func_index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    parent_map: dict[ast.AST, ast.AST],
    visited: frozenset[str] | None = None,
    depth: int = 0,
) -> list[tuple[ast.Call, str, list[str]]]:
    if depth >= TRANSITIVE_DEPTH_LIMIT:
        return []

    visited = visited or frozenset()
    results: list[tuple[ast.Call, str, list[str]]] = []

    for node in ast.walk(func_body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not func_body:
            continue

        if not isinstance(node, ast.Call):
            continue

        if _is_awaited(node, parent_map) or _is_in_safe_wrapper(node, parent_map):
            continue

        direct_name = _get_blocking_call_name(node, parent_map)
        if direct_name:
            results.append((node, direct_name, []))
            continue

        target = _resolve_call_target(node, func_index)
        if target is None or target.name in visited:
            continue

        deeper = _find_transitive_blocking(
            target,
            func_index,
            parent_map,
            visited | {target.name},
            depth + 1,
        )
        for blocking_node, blocking_name, chain in deeper:
            results.append((blocking_node, blocking_name, [target.name, *chain]))

    return results


class AsyncSyncRule(Rule):
    id: ClassVar[str] = "ASYNC001"
    description: ClassVar[str] = "Sync blocking call detected inside async FastAPI endpoint"
    severity: ClassVar[Severity] = Severity.WARNING
    tags: ClassVar[tuple[str, ...]] = ("async", "fastapi", "performance")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "async def" in source and (
            "@app." in source or "@router." in source or "FastAPI" in source or "APIRouter" in source
        )

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        parent_map = getattr(self, "_parent_map", None)
        func_index = getattr(self, "_func_index", None)
        if parent_map is None:
            parent_map = _build_parent_map(tree)
        if func_index is None:
            func_index = _build_function_index(tree)
        violations: list[Violation] = []
        seen: set[tuple[str, int, str]] = set()

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue

            if not any(_is_fastapi_route_decorator(d) for d in node.decorator_list):
                continue

            self._check_body(node, func_index, parent_map, filename, violations, seen)

            for dep_name in _extract_depends_targets(node):
                dep_func = func_index.get(dep_name)
                if dep_func is None:
                    continue
                self._check_body(
                    node,
                    func_index,
                    parent_map,
                    filename,
                    violations,
                    seen,
                    extra_entry=dep_func,
                    extra_label=f"Depends({dep_name})",
                )

        return violations

    def _check_body(
        self,
        endpoint: ast.AsyncFunctionDef,
        func_index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
        parent_map: dict[ast.AST, ast.AST],
        filename: str,
        violations: list[Violation],
        seen: set[tuple[str, int, str]],
        extra_entry: ast.FunctionDef | ast.AsyncFunctionDef | None = None,
        extra_label: str = "",
    ) -> None:
        bodies: list[ast.FunctionDef | ast.AsyncFunctionDef] = [endpoint]
        if extra_entry is not None:
            bodies.append(extra_entry)

        for body in bodies:
            is_depends = body is extra_entry
            transitive = _find_transitive_blocking(
                body,
                func_index,
                parent_map,
            )
            for blocking_node, blocking_name, chain in transitive:
                key = (filename, blocking_node.lineno, blocking_name)
                if key in seen:
                    continue
                seen.add(key)

                if is_depends and not chain:
                    assert extra_entry is not None
                    chain = [extra_entry.name]

                is_transitive = len(chain) > 0
                if is_transitive:
                    entry_func = chain[0]
                    call_path = " → ".join([*chain, blocking_name])
                    source = extra_label or endpoint.name
                    message = (
                        f"Transitive blocking call in async endpoint `{source}`: "
                        f"`{entry_func}()` reaches `{blocking_name}()` via {call_path}"
                    )
                    fix = FixSuggestion(
                        title=f"Wrap `{entry_func}()` call in `asyncio.to_thread()`",
                        replacement=f"await asyncio.to_thread({entry_func}, ...)",
                        explanation=(
                            f"`{entry_func}()` transitively calls `{blocking_name}()` "
                            f"which blocks the event loop. Wrap in `asyncio.to_thread()` "
                            f"or refactor to use async alternatives."
                        ),
                    )
                else:
                    message = f"Blocking sync call `{blocking_name}()` in async FastAPI endpoint `{endpoint.name}`"
                    fix = self._build_fix(blocking_name)

                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=message,
                        location=Location(
                            row=blocking_node.lineno,
                            column=blocking_node.col_offset + 1,
                        ),
                        end_location=Location(
                            row=blocking_node.end_lineno or blocking_node.lineno,
                            column=(blocking_node.end_col_offset or blocking_node.col_offset) + 1,
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
