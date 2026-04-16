# Smart Linter

Pluggable Python linter with heuristic rules, ruff-compatible output, and AI harness integration. Detects code quality issues that ruff cannot catch using AST analysis and heuristics.

## Why Smart Linter?

Ruff is excellent for style and syntax linting, but it runs entirely in Rust and does **not** support third-party plugins. Smart Linter fills the gap for heuristic rules that require Python-level AST analysis:

- Sync blocking calls inside async FastAPI endpoints
- SQL injection via string formatting
- Hardcoded secrets and dangerous deserialization
- Silent exception swallowing
- Late binding closures, mutable class attributes, and other logic bugs

## Install

Requires [uv](https://docs.astral.sh/uv/). No pip needed.

```bash
# Run directly without installing (one-shot)
uvx --from "git+https://github.com/agusmdev/smart-linter.git" smart-linter check src/

# Or install persistently
uv tool install "git+https://github.com/agusmdev/smart-linter.git"
smart-linter check src/

# With MCP server support (for AI agents)
uv tool install "git+https://github.com/agusmdev/smart-linter.git[mcp]"
```

## Quick Start

```bash
# Check your project
smart-linter check src/

# Get ruff-compatible JSON (merge with ruff output in CI)
smart-linter check src/ --format json

# Get AI-parseable fix suggestions
smart-linter check src/ --fix

# See what would change
smart-linter check src/ --diff

# Check only specific rules
smart-linter check src/ --select ASYNC001 ERR001 SEC001

# Ignore specific rules
smart-linter check src/ --ignore PERF001 PERF002

# List available rules
smart-linter list-rules .
```

## Rules

| Rule ID | Severity | Category | Description |
|---------|----------|----------|-------------|
| ASYNC001 | WARNING | async | Sync blocking calls in async FastAPI endpoints |
| ERR001 | WARNING | error-handling | Exception handlers that silently swallow errors |
| PERF001 | INFO | performance | String `+=` concatenation inside loops (O(n²)) |
| PERF002 | INFO | performance | Unnecessary list comprehension (use generator) |
| SEC001 | ERROR | security | SQL injection via string formatting in queries |
| SEC002 | ERROR | security | Hardcoded secrets/credentials in source code |
| SEC003 | ERROR | security | Dangerous deserialization (pickle, yaml.load) |
| RES001 | WARNING | reliability | Resources opened without context manager |
| MAIN001 | WARNING | bug | Mutable class attributes shared across instances |
| MAIN002 | WARNING | bug | Late binding closure in loops |
| LOGIC001 | WARNING | bug | Always-true or always-false conditions |

### ASYNC001 — Sync blocking calls in async endpoints

Detects synchronous blocking calls inside `async def` FastAPI route endpoints, including **transitive** calls through helper functions.

```python
# BAD — smart-linter flags this
@app.get("/users")
async def get_users():
    response = requests.get("https://api.example.com/users")  # ASYNC001
    return response.json()

# GOOD — use async alternatives
@app.get("/users")
async def get_users():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/users")
    return response.json()
```

**Detects:** `requests.*`, sync `httpx.*`, `time.sleep()`, `subprocess.run()`, `os.system()`, `open()`, `Path(...).read_text()`, `os.path.exists()`, `input()`.

**Safe wrappers** (not flagged): `asyncio.to_thread()`, `run_in_threadpool()`, `loop.run_in_executor()`, `anyio.to_thread.run_sync()`.

### ERR001 — Silent exception swallowing

Flags `except` handlers whose bodies contain no meaningful action — no logging, re-raise, return, or diagnostic calls.

```python
# BAD — silently swallows all errors
try:
    process_payment(order)
except Exception:
    pass  # ERR001

# GOOD — log or re-raise
try:
    process_payment(order)
except Exception:
    logger.exception("Payment processing failed")
    raise
```

### PERF001 — String concatenation in loops

String `+=` inside loops creates O(n²) new strings on each iteration.

```python
# BAD — O(n²) string building
result = ""
for item in items:
    result += f"Item: {item}\n"  # PERF001

# GOOD — use list + join
parts = []
for item in items:
    parts.append(f"Item: {item}\n")
result = "".join(parts)
```

### PERF002 — Unnecessary list comprehension

List comprehensions passed to functions that accept any iterable waste memory.

```python
# BAD — creates an intermediate list
has_match = any([x > threshold for x in data])  # PERF002

# GOOD — generator expression
has_match = any(x > threshold for x in data)
```

### SEC001 — SQL injection via string formatting

Detects SQL queries constructed with f-strings, `%` formatting, string concatenation, or `.format()`.

```python
# BAD — SQL injection vulnerability
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")  # SEC001

# GOOD — parameterized query
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

### SEC002 — Hardcoded secrets

Flags string assignments to variables matching secret patterns (`password`, `api_key`, `secret`, `token`, `private_key`, etc.).

```python
# BAD — secret in source code
database_url = "postgres://admin:s3cret@prod-db:5432/mydb"  # SEC002

# GOOD — use environment variables
database_url = os.environ["DATABASE_URL"]
```

### SEC003 — Dangerous deserialization

Flags calls to `pickle.loads()`, `yaml.load()` without `SafeLoader`, `marshal.loads()`, `shelve.open()`, and `jsonpickle.decode()`.

```python
# BAD — arbitrary code execution
data = pickle.loads(user_input)  # SEC003

# GOOD — use safe alternatives
data = json.loads(user_input)
```

### RES001 — Resources without context managers

Flags resource-creating calls assigned to variables outside `with` blocks.

```python
# BAD — resource leak if exception occurs before close()
f = open("data.txt")  # RES001
content = f.read()
f.close()

# GOOD — context manager ensures cleanup
with open("data.txt") as f:
    content = f.read()
```

### MAIN001 — Mutable class attributes

Mutable class-level `list`, `dict`, or `set` attributes are shared across all instances.

```python
# BAD — all instances share the same list
class EventHandler:
    events = []  # MAIN001

    def add_event(self, event):
        self.events.append(event)

# GOOD — define in __init__
class EventHandler:
    def __init__(self):
        self.events = []
```

### MAIN002 — Late binding closure in loops

Closures defined inside loops that reference loop variables by reference instead of by value.

```python
# BAD — all lambdas return the last value of i
funcs = []
for i in range(10):
    funcs.append(lambda: i)  # MAIN002

# GOOD — capture by value with default argument
funcs = []
for i in range(10):
    funcs.append(lambda i=i: i)
```

### LOGIC001 — Always-true/false conditions

Tautological or contradictory boolean conditions that likely indicate a logic error.

```python
# BAD — always True
if status == status:  # LOGIC001
    deploy()

# BAD — always False
if user.active and not user.active:  # LOGIC001
    revoke_access()

# GOOD — compare different variables
if status == expected_status:
    deploy()
```

## Real-World Catches

Issues found by Smart Linter in popular open-source projects:

### ASYNC001 in GPUSTack (6.4k stars)

[`gpustack/routes/worker/filesystem.py`](https://github.com/gpustack/gpustack/blob/main/gpustack/routes/worker/filesystem.py) — `os.path.exists()` is a blocking filesystem call inside an async endpoint:

```python
@router.get("/files/model-config")
async def read_model_config(path: str = Query(...)):
    validated_path = validate_path_security(path)
    if not os.path.exists(validated_path):  # ASYNC001
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
```

### ASYNC001 in GPT Researcher (19k+ stars)

[`backend/server/app.py`](https://github.com/assafelovic/gpt-researcher/blob/main/backend/server/app.py) — `os.path.exists()` and `open()` in async endpoints:

```python
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if not os.path.exists(index_path):  # ASYNC001
        raise HTTPException(status_code=404, detail="Frontend not found")
    with open(index_path, "r", encoding="utf-8") as f:  # ASYNC001
        content = f.read()
    return HTMLResponse(content=content)
```

### ASYNC001 in FastGPT (22k+ stars)

[`plugins/model/pdf-marker/api_mp.py`](https://github.com/labring/FastGPT/blob/main/plugins/model/pdf-marker/api_mp.py) — blocking `open()`, `os.makedirs()`, and `time.time()` in async file upload:

```python
@app.post("/v1/parse/file")
async def read_file(file: UploadFile = File(...)):
    start_time = time.time()  # ASYNC001
    os.makedirs(temp_dir, exist_ok=True)  # ASYNC001
    with open(temp_file_path, "wb") as temp_file:  # ASYNC001
        temp_file.write(await file.read())
```

### ASYNC001 in MONAI Label (Project MONAI, 700+ stars)

[`monailabel/endpoints/logs.py`](https://github.com/Project-MONAI/MONAILabel/blob/main/monailabel/endpoints/logs.py) — `subprocess.run()` in an async GPU info endpoint:

```python
@router.get("/gpu", summary="Get GPU Info (nvidia-smi)")
async def gpu_info(user: User = Depends(...)):
    response = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE)  # ASYNC001
    return response.stdout.decode("utf-8")
```

### ASYNC001 in LlamaFS (6k+ stars)

[`server.py`](https://github.com/iyaja/llama-fs/blob/main/server.py) — `os.path.exists()` in async batch endpoint:

```python
@app.post("/batch")
async def batch(request: Request):
    path = request.path
    if not os.path.exists(path):  # ASYNC001
        raise HTTPException(status_code=400, detail="Path does not exist")
```

### ERR001 in Netflix Dispatch (6.4k stars)

[`src/dispatch/database/service.py`](https://github.com/Netflix/dispatch/blob/main/src/dispatch/database/service.py) — silently swallowing exceptions when inspecting SQLAlchemy queries:

```python
try:
    if hasattr(compile_state, "_join_entities"):
        for mapper in compile_state._join_entities:
            if hasattr(mapper, "class_"):
                if mapper.class_ not in models:
                    models.append(mapper.class_)
except Exception:
    pass  # ERR001 — silently swallows all errors
```

### PERF001 in NVIDIA TensorRT-LLM

[`examples/scaffolding/contrib/DeepResearch/TavilyMCP/travily.py`](https://github.com/NVIDIA/TensorRT-LLM/blob/main/examples/scaffolding/contrib/DeepResearch/TavilyMCP/travily.py) — string concatenation in a loop building search results:

```python
@mcp.tool()
async def tavily_search(query: str) -> str:
    response = client.search(query=query)
    search_result = ""
    for result in response["results"]:
        search_result += f"{result['title']}: {result['content']}\n"  # PERF001
    return search_result
```

## Running Alongside Ruff

Smart Linter outputs ruff-compatible JSON. Merge both in your CI pipeline:

```bash
ruff check src/ --output-format json > lint-results.json
smart-linter check src/ --format json >> lint-results.json
```

Add to `ruff.toml` so `# noqa: ASYNC001` comments work:
```toml
[lint]
external = ["ASYNC001", "ERR001", "PERF001", "PERF002", "SEC001", "SEC002", "SEC003", "RES001", "MAIN001", "MAIN002", "LOGIC001"]
```

## Configuration

Add to `pyproject.toml`:

```toml
[tool.smart-linter]
# Enable specific rules (default: "all")
# select = ["ASYNC001", "SEC001"]

# Ignore specific rules
# ignore = []

# Custom rule paths (module:class format)
# custom-rules = ["my_package.rules:MyCustomRule"]

# Minimum severity: "error", "warning", "info"
# min-severity = "info"
```

## Writing Custom Rules

```python
import ast
from typing import ClassVar
from smart_linter.models import Rule, Violation, Location, Severity, FixSuggestion

class NoHardcodedSecretsRule(Rule):
    id: ClassVar[str] = "CUSTOM001"
    description: ClassVar[str] = "Potential hardcoded secret detected"
    severity: ClassVar[Severity] = Severity.ERROR

    def check(self, tree, filename: str = "") -> list[Violation]:
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "password" in target.id.lower():
                        violations.append(
                            Violation(
                                rule_id=self.id,
                                message=f"Hardcoded secret in variable `{target.id}`",
                                location=Location(row=node.lineno, column=node.col_offset),
                                severity=self.severity,
                                fix=FixSuggestion(
                                    title="Move secret to environment variable",
                                    replacement=f'{target.id} = os.environ["{target.id.upper()}"]',
                                    explanation="Never hardcode secrets. Use environment variables or a secrets manager.",
                                ),
                                filename=filename,
                            )
                        )
        return violations
```

Register in `pyproject.toml`:
```toml
[tool.smart-linter]
custom-rules = ["my_package.lint_rules:NoHardcodedSecretsRule"]
```

Or distribute as a package with entry points:
```toml
[project.entry-points."smart_linter.rules"]
secrets = "my_package.lint_rules:NoHardcodedSecretsRule"
```

## Pre-commit Hook

Add to `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: smart-linter
        name: smart-linter
        entry: smart-linter check
        language: system
        types: [python]
```

## AI Agent Integration

Smart Linter is designed for AI coding agents (Claude, Cursor, Copilot, etc.):

```bash
# Get structured fix data for AI consumption
smart-linter check src/ --fix

# Each violation includes:
# - fix_title: What to do
# - fix_replacement: Exact code to use
# - fix_explanation: Why this is wrong
```

### MCP Server (Native AI Integration)

Smart Linter ships an MCP server for direct integration with AI agents:

```bash
uv tool install "git+https://github.com/agusmdev/smart-linter.git[mcp]"
```

Add to your MCP client config (e.g. `.claude/settings.json`):
```json
{
  "mcpServers": {
    "smart-linter": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/agusmdev/smart-linter.git[mcp]", "python", "-m", "smart_linter.mcp_server"]
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `check_files` | Lint files and return violations with fix suggestions |
| `list_rules` | List all available rules |
| `explain_rule` | Get detailed explanation of a specific rule |

### Example MCP Usage

When connected, AI agents can directly:
- `check_files(paths=["src/api.py"])` — returns JSON violations with fixes
- `check_files(paths=["src/"], format="fixes")` — returns AI-parseable fix data
- `explain_rule(rule_id="ASYNC001")` — returns detection patterns and fix strategies

## Output Formats

### Text (default)
```
src/api.py:15:16: WARNING ASYNC001 Blocking sync call `requests.get()` in async FastAPI endpoint `get_users`
  💡 Replace `requests.get()` with async alternative
     Suggestion: await async_client.get(...)
```

### JSON (ruff-compatible)
```json
[{
  "code": "ASYNC001",
  "message": "Blocking sync call `requests.get()` in async FastAPI endpoint `get_users`",
  "severity": "warning",
  "filename": "src/api.py",
  "location": {"row": 15, "column": 16},
  "fix": {
    "applicability": "unsafe",
    "message": "Replace `requests.get()` with async alternative",
    "edits": [{"content": "await async_client.get(...)", ...}]
  }
}]
```

### SARIF (GitHub Code Scanning)
```bash
smart-linter check src/ --format sarif > results.sarif
```

## Requirements

- [uv](https://docs.astral.sh/uv/)
- Python 3.11+ (managed by uv automatically)

## License

MIT
