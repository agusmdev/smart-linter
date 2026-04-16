# Create Smart-Linter Rule

## Overview

This skill enables an AI agent to create a new smart-linter rule that integrates
correctly with the existing codebase. It provides the full contract, helper
reference, conventions, and validation steps.

## File Locations

| Artifact | Path |
|----------|------|
| Rule source | `src/smart_linter/rules/<snake_case_name>.py` |
| Rule tests | `tests/test_<rule_id_lower>_<snake_case_name>.py` |
| Registration | `pyproject.toml` → `[project.entry-points."smart_linter.rules"]` |
| Template | `templates/rule_template.py` |
| Benchmark | `bash benchmark-rules.sh <RULE_ID>` |

## Rule Contract

Every rule is a subclass of `smart_linter.models.Rule` with these ClassVars and methods:

### Required ClassVars

```python
class MyRule(Rule):
    id: ClassVar[str]          # e.g. "SEC004", "PERF003" — CATEGORY + 3-digit number
    description: ClassVar[str] # One-line human-readable description
    severity: ClassVar[Severity] = Severity.WARNING  # default; override as needed
    tags: ClassVar[tuple[str, ...]] = ("category",)  # free-form tags for filtering
```

### Rule ID Convention

Format: `CATEGORY` + 3-digit number. Existing categories:

| Prefix | Category | Existing IDs |
|--------|----------|-------------|
| `ASYNC` | Async/concurrency issues | ASYNC001 |
| `ERR` | Error handling | ERR001 |
| `PERF` | Performance | PERF001, PERF002 |
| `SEC` | Security | SEC001, SEC002, SEC003 |
| `RES` | Resource management | RES001 |
| `MAIN` | Maintainability | MAIN001, MAIN002 |
| `LOGIC` | Logic errors | LOGIC001 |

For new categories, use an uppercase 3–6 letter prefix (e.g. `TYPE`, `DEPREC`).

### Severity Convention

| Severity | When to use |
|----------|------------|
| `Severity.ERROR` | Security vulnerabilities, crash risks, data corruption |
| `Severity.WARNING` | Bugs, reliability issues, silent failures |
| `Severity.INFO` | Style, performance optimizations, best practices |

### `should_check(cls, source: str) -> bool` (class method)

- **Purpose**: Cheap string-level pre-filter. Called **before** AST parsing.
- **When to override**: Always. Return `False` for files that definitely don't contain
  the pattern you're looking for (e.g. `"except" not in source` for exception rules).
- **Default**: Returns `True` (always parse).

### `check(self, tree: ast.AST, filename: str = "") -> list[Violation]`

- **Receives**: Parsed AST tree and the filename being checked.
- **Returns**: List of `Violation` objects, one per detected issue.
- **Must** be implemented (base class raises `NotImplementedError`).

## AST Helper Reference (`smart_linter.ast_utils`)

### `build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]`

Returns a dict mapping every node → its parent node. Essential for checking
context (e.g. "is this statement inside a loop?").

```python
from smart_linter.ast_utils import build_parent_map
parent_map = build_parent_map(tree)
parent = parent_map.get(node)  # None if node is the root
```

### `get_qualified_name(node: ast.expr) -> str | None`

Returns the dotted name for `ast.Name` or `ast.Attribute` nodes.

```python
# requests.get  →  "requests.get"
# ast.Name(id="print")  →  "print"
# ast.Constant(value=1)  →  None
```

### `get_import_aliases(tree: ast.AST) -> dict[str, str]`

Returns `{local_name: original_module_path}` for all imports.

```python
# "import requests"           → {"requests": "requests"}
# "import numpy as np"        → {"np": "numpy"}
# "from os.path import join"  → {"join": "os.path.join"}
```

### `analyze_tree(tree: ast.AST) -> TreeAnalysis`

Single-pass analysis returning a `TreeAnalysis` dataclass with:

| Field | Type | Description |
|-------|------|-------------|
| `parent_map` | `dict[ast.AST, ast.AST]` | Same as `build_parent_map()` |
| `function_index` | `dict[str, FunctionDef \| AsyncFunctionDef]` | Top-level and nested functions by name |
| `imports` | `dict[str, str]` | Same as `get_import_aliases()` |
| `class_definitions` | `dict[str, ClassDef]` | Top-level classes by name |
| `string_constants` | `dict[str, list[Constant]]` | String literals mapped to their nodes |

Use when you need multiple analyses (avoids redundant walks).

### `is_in_context(node, parent_map, context_type) -> bool`

Walks up the parent chain. Returns `True` if `node` is inside a parent of
`context_type` (e.g. `ast.AsyncFunctionDef`, `ast.For`).

```python
if is_in_context(node, parent_map, ast.AsyncFunctionDef):
    # node is inside an async function
```

## Violation Construction

```python
Violation(
    rule_id=self.id,                   # from your ClassVar
    message="Human-readable description of the specific issue",
    location=Location(row=node.lineno, column=node.col_offset),
    end_location=Location(              # optional but recommended
        row=node.end_lineno or node.lineno,
        column=node.end_col_offset or node.col_offset,
    ),
    severity=self.severity,             # from your ClassVar
    fix=FixSuggestion(                  # optional but recommended
        title="Short fix title",
        replacement="code snippet showing the fix",
        explanation="Why this fix is correct",
    ),
    filename=filename,                  # passed through from check()
)
```

**Fields**: `rule_id`, `message`, `location` are required. `end_location`,
`fix`, and `filename` are optional but strongly recommended.

## Imports Pattern

```python
import ast
from typing import ClassVar

from smart_linter.ast_utils import build_parent_map, get_qualified_name, ...  # only what you need
from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)
```

## Registration in pyproject.toml

Add an entry under `[project.entry-points."smart_linter.rules"]`:

```toml
[project.entry-points."smart_linter.rules"]
# existing entries...
my_rule = "smart_linter.rules.my_rule:MyRuleName"   # snake_case = module:ClassName
```

## Test Convention

Tests live in `tests/test_<rule_id_lower>_<snake_case_name>.py`.

### Standard pattern:

```python
import ast
from smart_linter.rules.my_rule import MyRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = MyRule()
    return rule.check(tree, filename=filename)


def test_detects_violation():
    code = '''
# code that SHOULD trigger the rule
'''
    violations = _check_code(code)
    assert len(violations) >= 1
    assert violations[0].rule_id == "MYID"


def test_no_violation_clean_code():
    code = '''
# code that should NOT trigger the rule
'''
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_location():
    code = '''
# code with known line numbers
'''
    violations = _check_code(code)
    assert violations[0].location.row == 3  # adjust expected line
```

### Test guidelines:

- Use `_check_code()` helper to parse and run a single rule
- Name tests descriptively: `test_<what>_<expected_result>`
- Test at minimum: one positive case, one negative case, location correctness
- For rules with `should_check()`, add a test for it
- For rules with `FixSuggestion`, verify `fix.title` and `fix.replacement`

## Validation Checklist

After creating a rule, run through this checklist:

1. **Rule loads**: `uv run python -c "from smart_linter.rules.my_rule import MyRule; print('OK')"`
2. **Detects violations**: `uv run smart-linter check tests/fixtures/fastapi_example.py --select MYID`
3. **Zero false positives**: Create a clean code snippet and confirm the rule doesn't fire
4. **Tests pass**: `uv run pytest tests/test_my_rule.py -v`
5. **Full suite passes**: `uv run pytest` — no regressions
6. **Benchmark passes**: `bash benchmark-rules.sh MYID`

## Scope

### CAN:
- Create new files in `src/smart_linter/rules/`
- Create new test files in `tests/`
- Add entry to `pyproject.toml` under `[project.entry-points."smart_linter.rules"]`
- Use any helpers from `smart_linter.ast_utils`
- Reference the template at `templates/rule_template.py`

### MUST NOT:
- Modify existing rule files in `src/smart_linter/rules/`
- Modify existing test files
- Change `models.py`, `ast_utils.py`, `engine.py`, or `cli.py`
- Remove or alter existing entry_points
