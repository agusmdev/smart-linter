"""Tests for ASYNC001 rule: sync blocking calls in async FastAPI endpoints."""

import ast
from pathlib import Path

from smart_linter.rules.async_sync import AsyncSyncRule


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = AsyncSyncRule()
    return rule.check(tree, filename=filename)


def test_detects_requests_get_in_async_endpoint():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
async def get_data():
    response = requests.get("https://api.example.com")
    return response.json()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "ASYNC001"
    assert "requests.get" in violations[0].message


def test_detects_time_sleep_in_async_endpoint():
    code = """
import time
from fastapi import FastAPI
app = FastAPI()

@app.get("/slow")
async def slow():
    time.sleep(5)
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "time.sleep" in violations[0].message


def test_detects_subprocess_in_async_endpoint():
    code = """
import subprocess
from fastapi import FastAPI
app = FastAPI()

@app.get("/run")
async def run_cmd():
    result = subprocess.run(["echo", "hi"], capture_output=True)
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "subprocess.run" in violations[0].message


def test_no_violation_for_sync_def_endpoint():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
def get_data():
    response = requests.get("https://api.example.com")
    return response.json()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_non_endpoint_async():
    code = """
import requests

async def some_helper():
    response = requests.get("https://api.example.com")
    return response.json()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_safe_wrapper():
    code = """
import asyncio
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/safe")
async def safe():
    result = await asyncio.to_thread(requests.get, "https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_run_in_threadpool():
    code = """
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
import requests
app = FastAPI()

@app.get("/safe")
async def safe():
    result = await run_in_threadpool(requests.get, "https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_router_decorator():
    code = """
import requests
from fastapi import APIRouter
router = APIRouter()

@router.post("/create")
async def create():
    requests.post("https://api.example.com/create", json={})
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "requests.post" in violations[0].message


def test_detects_multiple_violations_in_one_endpoint():
    code = """
import time
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/bad")
async def bad():
    time.sleep(1)
    requests.get("https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_detects_os_system():
    code = """
import os
from fastapi import FastAPI
app = FastAPI()

@app.get("/cmd")
async def run():
    os.system("echo hello")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "os.system" in violations[0].message


def test_detects_input():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/input")
async def ask():
    name = input("Name: ")
    return {"name": name}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "input" in violations[0].message


def test_no_violation_for_normal_function():
    code = """
import time
import requests

def not_an_endpoint():
    time.sleep(1)
    requests.get("https://example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_has_fix_suggestion():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
async def get_data():
    requests.get("https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert violations[0].fix.replacement is not None
    assert "async_client" in violations[0].fix.replacement
    assert "httpx" in violations[0].fix.explanation


def test_time_sleep_fix_suggests_asyncio_sleep():
    code = """
import time
from fastapi import FastAPI
app = FastAPI()

@app.get("/slow")
async def slow():
    time.sleep(5)
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert "asyncio.sleep" in violations[0].fix.replacement


def test_full_fixture_file():
    fixture = FIXTURES_DIR / "fastapi_example.py"
    if not fixture.exists():
        return
    tree = ast.parse(fixture.read_text())
    rule = AsyncSyncRule()
    violations = rule.check(tree, filename=str(fixture))

    violation_calls = [v.message for v in violations]
    assert any("requests.get" in m and "bad_sync_request" in m for m in violation_calls)
    assert any("time.sleep" in m for m in violation_calls)
    assert any("subprocess.run" in m for m in violation_calls)
    assert any("requests.post" in m for m in violation_calls)

    good_endpoints = {
        "good_async",
        "good_safe_wrapper",
        "good_safe_threadpool",
        "no_false_positive",
    }
    for v in violations:
        for endpoint in good_endpoints:
            assert endpoint not in v.message

    assert not any("not_an_endpoint" in v.message for v in violations)
    assert not any("sync_def_endpoint" in v.message for v in violations)


def test_detects_open_call():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    with open("data.txt") as f:
        return f.read()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "open" in violations[0].message


def test_detects_bare_open():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    f = open("data.txt")
    content = f.read()
    return {"content": content}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "open" in violations[0].message


def test_detects_pathlib_read_text():
    code = """
from pathlib import Path
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    content = Path("data.txt").read_text()
    return {"content": content}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "Path(...).read_text" in violations[0].message


def test_detects_pathlib_write_text():
    code = """
from pathlib import Path
from fastapi import FastAPI
app = FastAPI()

@app.post("/file")
async def write_file():
    Path("data.txt").write_text("hello")
    return {"status": "ok"}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "Path(...).write_text" in violations[0].message


def test_detects_httpx_sync_client():
    code = """
import httpx
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
async def get_data():
    response = httpx.get("https://api.example.com")
    return response.json()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "httpx.get" in violations[0].message


def test_open_fix_suggests_aiofiles():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    f = open("data.txt")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert "aiofiles" in violations[0].fix.replacement


def test_pathlib_fix_suggests_anyio_path():
    code = """
from pathlib import Path
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    content = Path("data.txt").read_text()
    return {"content": content}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert "anyio.Path" in violations[0].fix.replacement


def test_no_violation_open_wrapped_in_aiofiles():
    code = """
import aiofiles
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    async with aiofiles.open("data.txt") as f:
        content = await f.read()
    return {"content": content}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_transitive_blocking_call():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

def _helper():
    return requests.get("https://api.example.com")

@app.get("/x")
async def get_x():
    data = _helper()
    return data
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "transitive" in violations[0].message.lower() or "_helper" in violations[0].message
    assert "requests.get" in violations[0].message


def test_detects_transitive_chain_depth_2():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

def _inner():
    requests.get("https://api.example.com")

def _outer():
    _inner()

@app.get("/x")
async def get_x():
    _outer()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "_outer" in violations[0].message
    assert "_inner" in violations[0].message


def test_no_transitive_flag_when_safe_wrapped():
    code = """
import asyncio, requests
from fastapi import FastAPI
app = FastAPI()

def _helper():
    return requests.get("https://api.example.com")

@app.get("/x")
async def get_x():
    data = await asyncio.to_thread(_helper)
    return data
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_depends_with_blocking():
    code = """
import requests
from fastapi import FastAPI, Depends
app = FastAPI()

def get_db():
    requests.get("https://internal/config")
    return "db"

@app.get("/x")
async def get_x(db=Depends(get_db)):
    return {"db": db}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "Depends(get_db)" in violations[0].message or "get_db" in violations[0].message


def test_recursive_call_no_infinite_loop():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

def _recursive(n):
    if n > 0:
        return _recursive(n - 1)
    return requests.get("https://api.example.com")

@app.get("/x")
async def get_x():
    return _recursive(5)
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_no_duplicate_violations():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

def _helper():
    requests.get("https://api.example.com")

@app.get("/x")
async def get_x():
    _helper()
    _helper()
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_transitive_and_direct_both_detected():
    code = """
import requests, time
from fastapi import FastAPI
app = FastAPI()

def _helper():
    requests.get("https://api.example.com")

@app.get("/x")
async def get_x():
    _helper()
    time.sleep(1)
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_transitive_fix_suggests_to_thread():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

def _helper():
    return requests.get("https://api.example.com")

@app.get("/x")
async def get_x():
    data = _helper()
    return data
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert "asyncio.to_thread(_helper" in violations[0].fix.replacement


def test_attribute_decorator_without_call():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get
async def get_data():
    requests.get("https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "requests.get" in violations[0].message


def test_name_decorator_not_route():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

my_decorator = lambda f: f

@my_decorator
@app.get("/data")
async def get_data():
    requests.get("https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_decorator_call_with_name_func():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@some_decorator()
@app.get("/data")
async def get_data():
    requests.get("https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_safe_wrapper_via_ensure_future():
    code = """
import asyncio
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/safe")
async def safe():
    result = asyncio.ensure_future(some_coroutine())
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_safe_wrapper_via_attribute_match():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/safe")
async def safe():
    result = await loop.run_in_executor(None, requests.get, "url")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_async_with_blocking_still_flagged():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    async with open("data.txt") as f:
        return f.read()
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_open_wrapped_in_anyio_open_file():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    await anyio.open_file(open("data.txt"))
    return {}
"""
    violations = _check_code(code)
    bare_open = [v for v in violations if "open" in v.message and "anyio" not in v.message]
    assert len(bare_open) == 0


def test_open_wrapped_in_aiofiles_open():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    await aiofiles.open(open("data.txt"))
    return {}
"""
    violations = _check_code(code)
    bare_open = [v for v in violations if "open" in v.message and "aiofiles.open" not in v.message]
    assert len(bare_open) == 0


def test_pathlib_path_class_method():
    code = """
import pathlib
from fastapi import FastAPI
app = FastAPI()

@app.get("/file")
async def read_file():
    content = pathlib.Path.read_text("data.txt")
    return {"content": content}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "Path(...).read_text" in violations[0].message


def test_depth_limit_transitive():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

def f1():
    requests.get("https://api.example.com")
    f2()
def f2(): f3()
def f3(): f4()
def f4(): f5()
def f5(): f6()
def f6(): requests.get("https://other.com")

@app.get("/x")
async def get_x():
    f1()
"""
    violations = _check_code(code)
    assert len(violations) >= 1
    assert any("requests.get" in v.message for v in violations)


def test_nested_function_def_skipped():
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/x")
async def get_x():
    def nested():
        pass
    requests.get("https://api.example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "requests.get" in violations[0].message


def test_should_check_with_fastapi_string():
    assert AsyncSyncRule.should_check("async def foo():\n    FastAPI()") is True


def test_depends_nonexistent_function():
    code = """
import requests
from fastapi import FastAPI, Depends
app = FastAPI()

@app.get("/x")
async def get_x(db=Depends(nonexistent_func)):
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_safe_wrapper_via_attr_match():
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/x")
async def handler():
    result = await custom_obj.run_in_threadpool(open("file"))
    return {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_anyio_open_file_wrapper():
    """Covers line 193: _is_wrapped_in_anyio_open_file anyio.open_file prefix."""
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/f")
async def read_f():
    await anyio.open_file(open("data.txt"))
    return {}
"""
    violations = _check_code(code)
    bare_open = [v for v in violations if "anyio" not in v.message and "open" in v.message]
    assert len(bare_open) == 0


def test_aiofiles_open_wrapper():
    """Covers line 194: _is_wrapped_in_anyio_open_file aiofiles.open prefix."""
    code = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/f")
async def read_f():
    await aiofiles.open(open("data.txt"))
    return {}
"""
    violations = _check_code(code)
    bare_open = [v for v in violations if "aiofiles" not in v.message and "open" in v.message]
    assert len(bare_open) == 0


def test_bare_name_blocking_call():
    """Covers line 232: bare name in BLOCKING_CALLS lookup."""
    code = """
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/x")
async def handler():
    requests.get("https://example.com")
    return {}
"""
    violations = _check_code(code)
    assert len(violations) >= 1
    assert "requests.get" in violations[0].message
