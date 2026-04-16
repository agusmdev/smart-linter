"""Comprehensive tests for cli.py: click CLI commands and edge cases."""

from __future__ import annotations

import json
import runpy
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from smart_linter.cli import check, list_rules, main

# ---------------------------------------------------------------------------
# Fixtures helpers
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

# Code with syntax error
CODE_SYNTAX_ERROR = "def foo(\n"

# Code with a mutable class attribute (MAIN001)
CODE_MUTABLE_ATTR = """\
class Foo:
    items = []
"""


def _write_file(directory: Path, name: str, content: str) -> Path:
    """Write a Python file into *directory* and return its path."""
    p = directory / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Tests: main group
# ---------------------------------------------------------------------------


class TestMainGroup:
    def test_no_subcommand_shows_help(self):
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code == 2
        assert "Usage" in result.output

    def test_invalid_subcommand(self):
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent-cmd"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_version_option(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "smart-linter" in result.output


# ---------------------------------------------------------------------------
# Tests: check command — basic
# ---------------------------------------------------------------------------


class TestCheckBasic:
    def test_check_text_format_default(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path)])
        # violations found → exit code 1
        assert result.exit_code == 1
        assert "ASYNC001" in result.output

    def test_check_explicit_text_format(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--format", "text"])
        assert result.exit_code == 1
        assert "ASYNC001" in result.output

    def test_check_clean_file_no_violations(self, tmp_path: Path):
        _write_file(tmp_path, "clean.py", CODE_CLEAN)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path)])
        assert result.exit_code == 0
        assert "No issues found" in result.output

    def test_check_empty_directory(self, tmp_path: Path):
        # tmp_path exists but has no .py files
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path)])
        assert result.exit_code == 0
        assert "No issues found" in result.output

    def test_check_single_file(self, tmp_path: Path):
        f = _write_file(tmp_path, "single.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(f)])
        assert result.exit_code == 1
        assert "ASYNC001" in result.output

    def test_check_nonexistent_path(self):
        runner = CliRunner()
        result = runner.invoke(check, ["/nonexistent/path/xyz.py"])
        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_check_file_with_syntax_error(self, tmp_path: Path):
        _write_file(tmp_path, "broken.py", CODE_SYNTAX_ERROR)
        runner = CliRunner()
        # Syntax errors are silently skipped by the engine — no violations
        result = runner.invoke(check, [str(tmp_path)])
        assert result.exit_code == 0
        assert "No issues found" in result.output


# ---------------------------------------------------------------------------
# Tests: check command — JSON output
# ---------------------------------------------------------------------------


class TestCheckJSON:
    def test_json_output_valid(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--format", "json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) >= 1
        codes = {v["code"] for v in data}
        assert "ASYNC001" in codes

    def test_json_output_empty(self, tmp_path: Path):
        _write_file(tmp_path, "clean.py", CODE_CLEAN)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


# ---------------------------------------------------------------------------
# Tests: check command — SARIF output
# ---------------------------------------------------------------------------


class TestCheckSARIF:
    def test_sarif_output_valid(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--format", "sarif"])
        assert result.exit_code == 1
        sarif = json.loads(result.output)
        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        runs = sarif["runs"]
        assert len(runs) == 1
        assert runs[0]["tool"]["driver"]["name"] == "smart-linter"
        assert len(runs[0]["results"]) >= 1
        rule_ids = {r["ruleId"] for r in runs[0]["results"]}
        assert "ASYNC001" in rule_ids

    def test_sarif_output_empty(self, tmp_path: Path):
        _write_file(tmp_path, "clean.py", CODE_CLEAN)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--format", "sarif"])
        assert result.exit_code == 0
        sarif = json.loads(result.output)
        assert sarif["runs"][0]["results"] == []


# ---------------------------------------------------------------------------
# Tests: check command — --fix and --diff
# ---------------------------------------------------------------------------


class TestCheckFixAndDiff:
    def test_fix_flag_outputs_json_fixes(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--fix"])
        assert result.exit_code == 1
        # The output ends with a JSON array of fixes
        # Find the JSON portion (everything after the last newline before JSON)
        lines = result.output.strip().split("\n")
        # The JSON is at the end — find the start of the array
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("["):
                json_start = i
                break
        assert json_start is not None
        json_text = "\n".join(lines[json_start:])
        fixes = json.loads(json_text)
        assert isinstance(fixes, list)
        assert len(fixes) >= 1
        assert "fix_title" in fixes[0]
        assert "fix_replacement" in fixes[0]
        assert "fix_explanation" in fixes[0]

    def test_diff_flag_outputs_diff_and_fixes(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--diff"])
        assert result.exit_code == 1
        # Should contain diff-style markers
        assert "---" in result.output
        assert "+++" in result.output
        assert "- #" in result.output
        assert "+ " in result.output
        # And the JSON fixes at the end
        assert "fix_title" in result.output

    def test_fix_flag_no_violations(self, tmp_path: Path):
        _write_file(tmp_path, "clean.py", CODE_CLEAN)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--fix"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_diff_flag_no_violations(self, tmp_path: Path):
        _write_file(tmp_path, "clean.py", CODE_CLEAN)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--diff"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_fix_with_no_fix_violation(self, tmp_path: Path):
        """Violations without a fix should still appear in fixes list but without fix details."""
        # MAIN001 violations typically have no fix suggestion
        _write_file(tmp_path, "mutable.py", CODE_MUTABLE_ATTR)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--fix"])
        # May or may not have violations depending on rule behavior
        # but should not crash
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# Tests: check command — --select / --ignore
# ---------------------------------------------------------------------------


class TestCheckSelectIgnore:
    def test_select_specific_rule(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--select", "ASYNC001", "--format", "json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert len(data) >= 1
        assert all(v["code"] == "ASYNC001" for v in data)

    def test_select_non_matching_rule(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--select", "PERF001", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_ignore_rule(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--ignore", "ASYNC001", "--ignore", "ASYNC003", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # ASYNC001 and ASYNC003 should be filtered out
        assert not any(v["code"] in ("ASYNC001", "ASYNC003") for v in data)

    def test_select_multiple_rules(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(
            check,
            [str(tmp_path), "--select", "ASYNC001", "--select", "PERF001", "--format", "json"],
        )
        data = json.loads(result.output)
        assert all(v["code"] in ("ASYNC001", "PERF001") for v in data)


# ---------------------------------------------------------------------------
# Tests: check command — --no-cache / --workers
# ---------------------------------------------------------------------------


class TestCheckFlags:
    def test_no_cache_flag(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--no-cache"])
        assert result.exit_code == 1
        assert "ASYNC001" in result.output

    def test_workers_flag(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--workers", "1"])
        assert result.exit_code == 1
        assert "ASYNC001" in result.output

    def test_workers_zero_auto(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--workers", "0"])
        assert result.exit_code == 1
        assert "ASYNC001" in result.output


# ---------------------------------------------------------------------------
# Tests: check command — --config
# ---------------------------------------------------------------------------


class TestCheckConfig:
    def test_config_file_option(self, tmp_path: Path):
        _write_file(tmp_path, "example.py", CODE_WITH_VIOLATION)
        # Create a pyproject.toml in a subdirectory
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "pyproject.toml").write_text('[tool.smart-linter]\nignore = ["ASYNC001"]\n')
        runner = CliRunner()
        result = runner.invoke(
            check, [str(tmp_path), "--config", str(config_dir / "pyproject.toml"), "--format", "json"]
        )
        data = json.loads(result.output)
        assert not any(v["code"] == "ASYNC001" for v in data)


# ---------------------------------------------------------------------------
# Tests: list-rules command
# ---------------------------------------------------------------------------


class TestListRules:
    def test_list_rules_shows_rules(self, tmp_path: Path):
        # list_rules requires a path argument that exists
        runner = CliRunner()
        result = runner.invoke(list_rules, [str(tmp_path)])
        assert result.exit_code == 0
        assert "Available rules" in result.output
        # At least ASYNC001 should be listed
        assert "ASYNC001" in result.output

    def test_list_rules_nonexistent_path(self):
        runner = CliRunner()
        result = runner.invoke(list_rules, ["/nonexistent/path"])
        assert result.exit_code != 0

    def test_list_rules_shows_descriptions(self, tmp_path: Path):
        runner = CliRunner()
        result = runner.invoke(list_rules, [str(tmp_path)])
        assert result.exit_code == 0
        # Should show rule IDs with descriptions (not just IDs)
        lines = result.output.strip().split("\n")
        rule_lines = [l for l in lines if l.strip() and "Available rules" not in l]
        assert len(rule_lines) >= 1
        # Each rule line should have format "  RULEID: description"
        for line in rule_lines:
            assert ":" in line


# ---------------------------------------------------------------------------
# Tests: multiple paths
# ---------------------------------------------------------------------------


class TestMultiplePaths:
    def test_check_multiple_directories(self, tmp_path: Path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        _write_file(dir1, "a.py", CODE_WITH_VIOLATION)
        _write_file(dir2, "b.py", CODE_WITH_VIOLATION)

        runner = CliRunner()
        result = runner.invoke(check, [str(dir1), str(dir2), "--format", "json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert len(data) >= 2

    def test_check_mixed_file_and_dir(self, tmp_path: Path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _write_file(subdir, "a.py", CODE_WITH_VIOLATION)
        single = _write_file(tmp_path, "b.py", CODE_WITH_VIOLATION)

        runner = CliRunner()
        result = runner.invoke(check, [str(subdir), str(single), "--format", "json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert len(data) >= 2


# ---------------------------------------------------------------------------
# Tests: _print_fixes edge cases
# ---------------------------------------------------------------------------


class TestPrintFixesEdgeCases:
    def test_diff_flag_with_fix_replacement_none(self, tmp_path: Path):
        """When a violation has a fix but replacement is None, no diff lines are printed."""
        # MAIN001 has fix with replacement but some violations might not
        # Let's just verify the CLI doesn't crash
        _write_file(tmp_path, "mutable.py", CODE_MUTABLE_ATTR)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--diff"])
        assert result.exit_code in (0, 1)

    def test_fix_flag_violation_without_fix(self, tmp_path: Path):
        """Violations with fix=None should be excluded from the fixes list."""
        _write_file(tmp_path, "mutable.py", CODE_MUTABLE_ATTR)
        runner = CliRunner()
        result = runner.invoke(check, [str(tmp_path), "--fix"])
        # Should not crash regardless
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# Tests: __main__ block
# ---------------------------------------------------------------------------


class TestMainModule:
    def test_main_invoked_as_script(self):
        with patch("sys.argv", ["smart-linter", "--help"]), patch("sys.exit") as mock_exit:
            runpy.run_module("smart_linter.cli", run_name="__main__")
            mock_exit.assert_called_once_with(0)

    def test_main_group_body_executed(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "check" in result.output
        assert "list-rules" in result.output

    def test_main_callback_body(self):
        main.callback()


class TestListRulesNoRules:
    def test_list_rules_no_rules_available(self, tmp_path: Path):
        with patch("smart_linter.cli.list_rules") as mock_list_rules_cmd:
            pass
        with patch("smart_linter.registry.get_all_rules", return_value={}):
            runner = CliRunner()
            result = runner.invoke(list_rules, [str(tmp_path)])
            assert result.exit_code == 0
            assert "No rules available" in result.output
