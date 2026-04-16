"""Tests for smart_linter.config."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from smart_linter.config import DEFAULT_EXCLUDE, Config


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestConfigDefaults:
    def test_default_select(self):
        cfg = Config()
        assert cfg.select == ["all"]

    def test_default_ignore(self):
        cfg = Config()
        assert cfg.ignore == []

    def test_default_custom_rules(self):
        cfg = Config()
        assert cfg.custom_rules == []

    def test_default_min_severity(self):
        cfg = Config()
        assert cfg.min_severity == "info"

    def test_default_exclude(self):
        cfg = Config()
        assert cfg.exclude == list(DEFAULT_EXCLUDE)

    def test_default_no_cache(self):
        cfg = Config()
        assert cfg.no_cache is False

    def test_default_workers(self):
        cfg = Config()
        assert cfg.workers == 0


# ---------------------------------------------------------------------------
# Custom values via constructor
# ---------------------------------------------------------------------------


class TestConfigCustom:
    def test_custom_select(self):
        cfg = Config(select=["ASYNC001", "ERR001"])
        assert cfg.select == ["ASYNC001", "ERR001"]

    def test_custom_ignore(self):
        cfg = Config(ignore=["PERF001"])
        assert cfg.ignore == ["PERF001"]

    def test_custom_custom_rules(self):
        cfg = Config(custom_rules=["my_pkg.rules:MyRule"])
        assert cfg.custom_rules == ["my_pkg.rules:MyRule"]

    def test_custom_min_severity(self):
        cfg = Config(min_severity="error")
        assert cfg.min_severity == "error"

    def test_custom_exclude(self):
        cfg = Config(exclude=["custom_dir"])
        assert cfg.exclude == ["custom_dir"]

    def test_custom_no_cache(self):
        cfg = Config(no_cache=True)
        assert cfg.no_cache is True

    def test_custom_workers(self):
        cfg = Config(workers=4)
        assert cfg.workers == 4


# ---------------------------------------------------------------------------
# DEFAULT_EXCLUDE
# ---------------------------------------------------------------------------


class TestDefaultExclude:
    def test_contains_common_patterns(self):
        expected = [
            "node_modules",
            ".git",
            "__pycache__",
            ".venv",
            "venv",
            "build",
            "dist",
            ".eggs",
            "*.egg-info",
            ".smart_linter_cache",
        ]
        for pattern in expected:
            assert pattern in DEFAULT_EXCLUDE

    def test_is_list(self):
        assert isinstance(DEFAULT_EXCLUDE, list)


# ---------------------------------------------------------------------------
# Config.from_pyproject
# ---------------------------------------------------------------------------


class TestFromPyproject:
    def test_missing_pyproject_returns_defaults(self, tmp_path: Path):
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.select == ["all"]
        assert cfg.ignore == []
        assert cfg.no_cache is False

    def test_reads_tool_smart_linter_section(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
                [tool.smart-linter]
                select = ["ASYNC001"]
                ignore = ["PERF001"]
                min-severity = "error"
                no-cache = true
                workers = 8
            """)
        )
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.select == ["ASYNC001"]
        assert cfg.ignore == ["PERF001"]
        assert cfg.min_severity == "error"
        assert cfg.no_cache is True
        assert cfg.workers == 8

    def test_partial_config_fills_defaults(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
                [tool.smart-linter]
                select = ["ASYNC001"]
            """)
        )
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.select == ["ASYNC001"]
        assert cfg.ignore == []
        assert cfg.min_severity == "info"
        assert cfg.no_cache is False
        assert cfg.workers == 0

    def test_custom_rules_from_pyproject(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
                [tool.smart-linter]
                custom-rules = ["my_pkg.rules:MyRule", "other:Rule2"]
            """)
        )
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.custom_rules == ["my_pkg.rules:MyRule", "other:Rule2"]

    def test_custom_exclude_from_pyproject(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            textwrap.dedent("""\
                [tool.smart-linter]
                exclude = ["custom_dir", "other_dir"]
            """)
        )
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.exclude == ["custom_dir", "other_dir"]

    def test_no_project_root_defaults_to_cwd(self):
        cfg = Config.from_pyproject()
        assert isinstance(cfg, Config)

    def test_invalid_toml_returns_defaults(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("this is not valid toml {{{")
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.select == ["all"]

    def test_no_tool_section_returns_defaults(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[tool.other]\nkey = 'value'\n")
        cfg = Config.from_pyproject(tmp_path)
        assert cfg.select == ["all"]
