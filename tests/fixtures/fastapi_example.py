"""Test fixture: async FastAPI endpoint with various sync blocking calls."""

from fastapi import FastAPI, APIRouter
import requests
import time
import subprocess
import os

app = FastAPI()
router = APIRouter()


@app.get("/bad-sync-request")
async def bad_sync_request():
    response = requests.get("https://api.example.com/data")
    return {"data": response.json()}


@app.post("/bad-sync-sleep")
async def bad_sync_sleep():
    time.sleep(5)
    return {"status": "done"}


@app.get("/bad-sync-subprocess")
async def bad_sync_subprocess():
    result = subprocess.run(["echo", "hello"], capture_output=True, text=True)
    return {"output": result.stdout}


@router.get("/bad-router-sync")
async def bad_router_sync():
    response = requests.post("https://api.example.com/create", json={"key": "value"})
    return response.json()


@app.get("/good-async")
async def good_async():
    import asyncio

    await asyncio.sleep(1)
    return {"status": "ok"}


@app.get("/good-safe-wrapper")
async def good_safe_wrapper():
    import asyncio

    result = await asyncio.to_thread(requests.get, "https://api.example.com/data")
    return {"data": result.json()}


@app.get("/good-safe-threadpool")
async def good_safe_threadpool():
    from fastapi.concurrency import run_in_threadpool

    result = await run_in_threadpool(requests.get, "https://api.example.com/data")
    return {"data": result.json()}


def sync_helper():
    return requests.get("https://api.example.com/data")


@app.get("/no-false-positive-sync-helper")
async def no_false_positive():
    import asyncio

    result = await asyncio.to_thread(sync_helper)
    return {"data": result}


@app.get("/bad-multiple-violations")
async def bad_multiple():
    import time

    time.sleep(1)
    result = requests.get("https://api.example.com/data")
    output = subprocess.run(["ls"], capture_output=True)
    return {"done": True}


@app.get("/bad-os-system")
async def bad_os_system():
    os.system("echo hello")
    return {"done": True}


@app.get("/bad-input")
async def bad_input():
    name = input("Enter your name: ")
    return {"name": name}


@app.get("/bad-os-path")
async def bad_os_path():
    import os.path

    exists = os.path.exists("/some/file.txt")
    return {"exists": exists}


def not_an_endpoint():
    time.sleep(1)
    requests.get("https://example.com")
    return "not checked"


@app.get("/sync-def-endpoint")
def sync_def_endpoint():
    response = requests.get("https://api.example.com/data")
    return {"data": response.json()}
