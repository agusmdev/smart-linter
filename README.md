# Smart Linter

Pluggable Python linter with heuristic rules, ruff-compatible output, and AI harness integration. Detects code quality issues that ruff cannot catch using AST analysis and heuristics.

## Why Smart Linter?

Ruff is excellent for style and syntax linting, but it runs entirely in Rust and does **not** support third-party plugins. Smart Linter fills the gap for heuristic rules that require Python-level AST analysis:

- Sync blocking calls inside async FastAPI endpoints
- Complex pattern detection requiring import resolution or type inference
- Best-practice rules specific to frameworks (FastAPI, Django, etc.)

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
```

## First Rule: ASYNC001

Detects sync blocking calls inside `async def` FastAPI endpoints:

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

### What ASYNC001 Detects

| Blocking Call | Async Alternative |
|---|---|
| `requests.get/post/...` | `httpx.AsyncClient` |
| `httpx.get/post/...` (sync) | `httpx.AsyncClient` |
| `time.sleep(n)` | `await asyncio.sleep(n)` |
| `subprocess.run/call/...` | `asyncio.create_subprocess_exec` |
| `os.system()` | `asyncio.create_subprocess_shell` |
| `open()` / `with open(...)` | `aiofiles.open()` / `anyio.open_file()` |
| `Path("x").read_text()` | `await anyio.Path("x").read_text()` |
| `os.path.exists/isdir/...` | `asyncio.to_thread(os.path.exists, ...)` |
| `input()` | `await asyncio.to_thread(input, ...)` |

### Safe Wrappers (No False Positives)

Calls wrapped in these are **not** flagged:

```python
await asyncio.to_thread(sync_function, ...)
await run_in_threadpool(sync_function, ...)
await loop.run_in_executor(None, sync_function, ...)
await anyio.to_thread.run_sync(sync_function, ...)
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
external = ["ASYNC001"]
```

## Configuration

Add to `pyproject.toml`:

```toml
[tool.smart-linter]
# Enable specific rules (default: "all")
# select = ["ASYNC001"]

# Ignore specific rules
# ignore = []

# Custom rule paths (module:class format)
# custom-rules = ["my_package.rules:MyCustomRule"]

# Minimum severity: "error", "warning", "info"
# min-severity = "info"
```

## Writing Custom Rules

```python
# my_project/lint_rules.py
import ast
from typing import ClassVar
from smart_linter.models import Rule, Violation, Location, Severity, FixSuggestion

class NoHardcodedSecretsRule(Rule):
    id: ClassVar[str] = "SEC001"
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
custom-rules = ["my_project.lint_rules:NoHardcodedSecretsRule"]
```

Or distribute as a package with entry points:
```toml
[project.entry-points."smart_linter.rules"]
secrets = "my_project.lint_rules:NoHardcodedSecretsRule"
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

Or for Cursor (`.cursor/mcp.json`):
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

See `CLAUDE.md` in the repository for full AI integration instructions.

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
