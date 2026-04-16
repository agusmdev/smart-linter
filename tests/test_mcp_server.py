"""Comprehensive tests for mcp_server.py — MCP tools and server entry point."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from smart_linter.mcp_server import check_files, explain_rule, list_rules, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Code that triggers ASYNC001 (sync blocking call in async FastAPI endpoint)
CODE_WITH_VIOLATION = """\
import requests
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
async def get_data() -> dict:
    response = requests.get("https://api.example.com")
    return response.json()
"""

# Code that is clean — no violations expected
CODE_CLEAN = """\
import asyncio
from fastapi import FastAPI
app = FastAPI()

@app.get("/data")
async def get_data() -> dict:
    await asyncio.sleep(1)
    return {}
"""

# Code with a mutable class attribute (MAIN001)
CODE_MUTABLE_ATTR = """\
class Foo:
    items = []
"""

# Code with string concatenation in a loop (PERF001)
CODE_PERF001 = """\
result = ""
for item in items:
    result += str(item)
"""


def _write_file(directory: Path, name: str, content: str) -> Path:
    """Write a Python file into *directory* and return its path."""
    p = directory / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# check_files — JSON format (default)
# ---------------------------------------------------------------------------


class TestCheckFilesJsonFormat:
    def test_json_format_default(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)])
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["code"] == "ASYNC001"

    def test_json_format_explicit(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], output_format="json")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_json_format_empty_violations(self, tmp_path: Path):
        f = _write_file(tmp_path, "clean.py", CODE_CLEAN)
        result = check_files(paths=[str(f)], output_format="json")
        data = json.loads(result)
        assert data == []

    def test_json_format_directory_path(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(tmp_path)], output_format="json")
        data = json.loads(result)
        assert len(data) >= 1


# ---------------------------------------------------------------------------
# check_files — text format
# ---------------------------------------------------------------------------


class TestCheckFilesTextFormat:
    def test_text_format_with_violations(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], output_format="text")
        assert "ASYNC001" in result
        assert "WARNING" in result

    def test_text_format_clean_file(self, tmp_path: Path):
        f = _write_file(tmp_path, "clean.py", CODE_CLEAN)
        result = check_files(paths=[str(f)], output_format="text")
        assert result == "No issues found."


# ---------------------------------------------------------------------------
# check_files — fixes format
# ---------------------------------------------------------------------------


class TestCheckFilesFixesFormat:
    def test_fixes_format_with_violations(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], output_format="fixes")
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        entry = data[0]
        assert "file" in entry
        assert "line" in entry
        assert "column" in entry
        assert "rule" in entry
        assert "severity" in entry
        assert "message" in entry
        assert entry["rule"] == "ASYNC001"

    def test_fixes_format_includes_fix_fields(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], output_format="fixes")
        data = json.loads(result)
        entry = data[0]
        # ASYNC001 violations have fix suggestions
        assert "fix_title" in entry
        assert "fix_replacement" in entry
        assert "fix_explanation" in entry
        assert "Replace" in entry["fix_title"]

    def test_fixes_format_violation_without_fix(self, tmp_path: Path):
        """Violations without a fix should not include fix_title etc."""
        f = _write_file(tmp_path, "mutable.py", CODE_MUTABLE_ATTR)
        result = check_files(paths=[str(f)], output_format="fixes")
        data = json.loads(result)
        if len(data) > 0:
            entry = data[0]
            assert "file" in entry
            assert "rule" in entry

    def test_fixes_format_no_violations(self, tmp_path: Path):
        f = _write_file(tmp_path, "clean.py", CODE_CLEAN)
        result = check_files(paths=[str(f)], output_format="fixes")
        data = json.loads(result)
        assert data == []


# ---------------------------------------------------------------------------
# check_files — select / ignore filters
# ---------------------------------------------------------------------------


class TestCheckFilesSelectIgnore:
    def test_select_filters_rules(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], select=["ASYNC001"], output_format="json")
        data = json.loads(result)
        assert len(data) >= 1
        assert all(v["code"] == "ASYNC001" for v in data)

    def test_select_non_matching_rule(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], select=["PERF001"], output_format="json")
        data = json.loads(result)
        assert data == []

    def test_ignore_rule(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], ignore=["ASYNC001"], output_format="json")
        data = json.loads(result)
        assert not any(v["code"] == "ASYNC001" for v in data)

    def test_select_and_ignore_combined(self, tmp_path: Path):
        f = _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f)], select=["ASYNC001", "PERF001"], ignore=["ASYNC001"], output_format="json")
        data = json.loads(result)
        assert not any(v["code"] == "ASYNC001" for v in data)


# ---------------------------------------------------------------------------
# check_files — multiple paths
# ---------------------------------------------------------------------------


class TestCheckFilesMultiplePaths:
    def test_multiple_files(self, tmp_path: Path):
        f1 = _write_file(tmp_path, "a.py", CODE_WITH_VIOLATION)
        f2 = _write_file(tmp_path, "b.py", CODE_WITH_VIOLATION)
        result = check_files(paths=[str(f1), str(f2)], output_format="json")
        data = json.loads(result)
        assert len(data) >= 2

    def test_nonexistent_path_returns_empty(self, tmp_path: Path):
        result = check_files(paths=[str(tmp_path / "nonexistent.py")], output_format="json")
        data = json.loads(result)
        assert data == []


# ---------------------------------------------------------------------------
# list_rules
# ---------------------------------------------------------------------------


class TestListRules:
    def test_list_rules_returns_sorted_json(self):
        result = list_rules()
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) >= 1
        # Should be sorted by rule ID
        ids = [r["id"] for r in data]
        assert ids == sorted(ids)

    def test_list_rules_has_required_fields(self):
        result = list_rules()
        data = json.loads(result)
        for rule in data:
            assert "id" in rule
            assert "description" in rule
            assert "severity" in rule
            assert "tags" in rule

    def test_list_rules_includes_known_rules(self):
        result = list_rules()
        data = json.loads(result)
        ids = {r["id"] for r in data}
        assert "ASYNC001" in ids
        assert "ERR001" in ids
        assert "SEC001" in ids

    def test_list_rules_tags_is_list(self):
        result = list_rules()
        data = json.loads(result)
        async001 = next(r for r in data if r["id"] == "ASYNC001")
        assert isinstance(async001["tags"], list)
        assert "async" in async001["tags"]


# ---------------------------------------------------------------------------
# explain_rule — known rules
# ---------------------------------------------------------------------------


class TestExplainRule:
    def test_explain_async001_detailed(self):
        result = explain_rule(rule_id="ASYNC001")
        data = json.loads(result)
        assert data["id"] == "ASYNC001"
        assert data["description"] == "Sync blocking call detected inside async FastAPI endpoint"
        assert data["severity"] == "warning"
        assert "tags" in data
        assert "title" in data
        assert data["title"] == "Sync blocking call in async FastAPI endpoint"
        assert "safe_wrappers" in data
        assert isinstance(data["safe_wrappers"], list)
        assert "asyncio.to_thread(func, ...)" in data["safe_wrappers"]
        assert "detection_patterns" in data
        assert isinstance(data["detection_patterns"], list)
        assert len(data["detection_patterns"]) > 0
        assert "pathlib_methods" in data
        assert "read_text" in data["pathlib_methods"]
        assert "false_positive_prevention" in data
        assert "Does NOT flag" in data["false_positive_prevention"]

    def test_explain_non_async001_rule_basic_info(self):
        """Non-ASYNC001 rules should return basic info without detection patterns."""
        result = explain_rule(rule_id="ERR001")
        data = json.loads(result)
        assert data["id"] == "ERR001"
        assert "description" in data
        assert "severity" in data
        assert "tags" in data
        # Should NOT have ASYNC001-specific fields
        assert "title" not in data
        assert "safe_wrappers" not in data
        assert "detection_patterns" not in data

    def test_explain_unknown_rule_returns_error(self):
        result = explain_rule(rule_id="UNKNOWN999")
        data = json.loads(result)
        assert "error" in data
        assert "UNKNOWN999" in data["error"]

    def test_explain_sec001_basic_info(self):
        result = explain_rule(rule_id="SEC001")
        data = json.loads(result)
        assert data["id"] == "SEC001"
        assert data["severity"] == "error"


# ---------------------------------------------------------------------------
# main() — server start
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_calls_mcp_run(self):
        with patch("smart_linter.mcp_server.mcp") as mock_mcp:
            main()
            mock_mcp.run.assert_called_once_with(transport="stdio")


# ---------------------------------------------------------------------------
# ImportError guard and __main__ entry point
# ---------------------------------------------------------------------------


class TestImportErrorGuard:
    def test_import_error_exits(self):
        with patch.dict("sys.modules", {"mcp": None, "mcp.server": None, "mcp.server.fastmcp": None}):
            with pytest.raises(SystemExit) as exc_info:
                import importlib

                import smart_linter.mcp_server as mod

                importlib.reload(mod)
            assert exc_info.value.code == 1

    def test_dunder_main_runs_main(self):
        from unittest.mock import MagicMock

        import smart_linter.mcp_server as mod

        mock_mcp = MagicMock()
        with patch.object(mod, "mcp", mock_mcp):
            code = 'if __name__ == "__main__":\n    main()'
            exec(
                compile(code, mod.__file__, "exec"),
                {"__name__": "__main__", "main": mod.main, "mcp": mock_mcp, "__builtins__": __builtins__},
            )
            mock_mcp.run.assert_called_once_with(transport="stdio")
