# Smart Linter — AI Agent Integration

## For AI Coding Agents (Claude, Cursor, Copilot, etc.)

Smart Linter detects heuristic code quality issues that ruff cannot catch. Run it alongside ruff.

## Install

```bash
# Install with uv
uv tool install "git+https://github.com/agusmdev/smart-linter.git"

# Or run one-shot without installing
uvx --from "git+https://github.com/agusmdev/smart-linter.git" smart-linter check src/
```

## Commands

```bash
# Check for issues
smart-linter check src/

# Get JSON output (merge with ruff for unified CI view)
smart-linter check src/ --format json

# Get AI-parseable fix suggestions (use this for auto-correction)
smart-linter check src/ --fix

# Get diff-style output showing what would change
smart-linter check src/ --diff

# Check only specific rules
smart-linter check src/ --select ASYNC001 ERR001 SEC001

# Ignore specific rules
smart-linter check src/ --ignore PERF001 PERF002

# Disable caching (force fresh run)
smart-linter check src/ --no-cache

# Control parallel workers (0 = auto, based on CPU count)
smart-linter check src/ --workers 4

# List available rules
smart-linter list-rules .
```

## Integration with ruff

Smart Linter outputs ruff-compatible JSON. Merge results in CI:

```bash
# Run both linters and merge JSON output
ruff check src/ --output-format json > lint-results.json
smart-linter check src/ --format json >> lint-results.json
```

Add to `ruff.toml` so `# noqa: ASYNC001` comments work:
```toml
[lint]
external = ["ASYNC001", "ASYNC003", "ERR001", "ERR002", "FAST001", "PERF001", "PERF002", "SEC001", "SEC002", "SEC003", "SEC004", "SEC006", "RES001", "RESP001", "MAIN001", "MAIN002", "LOGIC001"]
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

## Fix Workflow for AI Agents

When smart-linter reports issues:

1. Run `smart-linter check --fix` to get structured fix suggestions
2. Each violation includes: `fix_title`, `fix_replacement`, `fix_explanation`
3. Apply the suggested replacement to the flagged line
4. Re-run to verify the fix resolved the issue

## MCP Server (Native AI Integration)

Smart Linter ships an MCP server for direct integration with AI agents (Claude, Cursor, Copilot):

```bash
# Install with MCP support
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

## Available Rules

| Rule ID | Description | Severity |
|---------|-------------|----------|
| ASYNC001 | Detects sync blocking calls in async FastAPI endpoints | WARNING |
| ASYNC003 | Detects async functions without await (should use `def`) | WARNING |
| ERR001 | Detects exception handlers that silently swallow errors | WARNING |
| ERR002 | Detects raise inside except without `from` (lost context) | WARNING |
| FAST001 | Detects BaseHTTPMiddleware usage (use pure ASGI instead) | WARNING |
| PERF001 | String concatenation using += inside loop (O(n²)) | INFO |
| PERF002 | Unnecessary list comprehension (use generator expression) | INFO |
| SEC001 | SQL injection via string formatting in queries | ERROR |
| SEC002 | Hardcoded secrets/credentials in source code | ERROR |
| SEC003 | Dangerous deserialization (pickle, yaml.load without safe Loader) | ERROR |
| SEC004 | Unauthenticated mutation endpoints (POST/PUT/DELETE/PATCH without auth) | ERROR |
| SEC006 | JWT decode without explicit algorithm (algorithm confusion attack) | ERROR |
| RES001 | Resources opened without context manager (resource leak risk) | WARNING |
| RESP001 | Missing response_model on API endpoint | WARNING |
| MAIN001 | Mutable class attributes shared across all instances | WARNING |
| MAIN002 | Late binding closure in loops (captures loop variable by reference) | WARNING |
| LOGIC001 | Always-true or always-false conditions (logic errors) | WARNING |

## Writing Custom Rules

```python
import ast
from typing import ClassVar
from smart_linter.models import Rule, Violation, Location, Severity, FixSuggestion

class MyRule(Rule):
    id: ClassVar[str] = "CUSTOM001"
    description: ClassVar[str] = "Description of what this rule detects"
    severity: ClassVar[Severity] = Severity.WARNING

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "pattern" in source

    def check(self, tree, filename: str = "") -> list[Violation]:
        violations = []
        for node in ast.walk(tree):
            pass
        return violations
```

Register in `pyproject.toml`:
```toml
[tool.smart-linter]
custom-rules = ["my_package.my_rules:MyRule"]
```
