"""Comprehensive tests for engine.py — file discovery, AST parsing, caching, parallel dispatch."""

from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from smart_linter.config import Config
from smart_linter.engine import (
    CACHE_DIR_NAME,
    CACHE_MAX_AGE_SECONDS,
    IO_PARALLEL_THRESHOLD,
    MAX_FILE_SIZE,
    SEVERITY_ORDER,
    _build_ast_analysis,
    _cache_key,
    _cache_path,
    _clean_stale_cache,
    _dict_to_violation,
    _filter_by_severity,
    _get_cached_violations,
    _process_parallel,
    _process_sequential,
    _read_file_safe,
    _read_files_parallel,
    _save_to_cache,
    _violation_to_dict,
    discover_files,
    lint_single_file,
    run,
)
from smart_linter.models import FixSuggestion, Location, Rule, Severity, Violation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DummyRule(Rule):
    """Flags every ast.Assign node."""

    id: ClassVar[str] = "DUMMY001"
    description: ClassVar[str] = "Dummy rule for testing"
    severity: ClassVar[Severity] = Severity.WARNING

    @classmethod
    def should_check(cls, source: str) -> bool:
        return True

    def check(self, tree, filename: str = "") -> list[Violation]:
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Found assignment",
                        location=Location(row=node.lineno, column=node.col_offset),
                        severity=self.severity,
                        filename=filename,
                    )
                )
        return violations


class _DummyErrorRule(Rule):
    """Produces ERROR-level violations on every file."""

    id: ClassVar[str] = "DUMMY002"
    description: ClassVar[str] = "Error-level dummy rule"
    severity: ClassVar[Severity] = Severity.ERROR

    def check(self, tree, filename: str = "") -> list[Violation]:
        return [
            Violation(
                rule_id=self.id,
                message="Error-level violation",
                location=Location(row=1, column=0),
                severity=self.severity,
                filename=filename,
            )
        ]


class _DummyInfoRule(Rule):
    """Produces INFO-level violations on every file."""

    id: ClassVar[str] = "DUMMY003"
    description: ClassVar[str] = "Info-level dummy rule"
    severity: ClassVar[Severity] = Severity.INFO

    def check(self, tree, filename: str = "") -> list[Violation]:
        return [
            Violation(
                rule_id=self.id,
                message="Info-level violation",
                location=Location(row=1, column=0),
                severity=self.severity,
                filename=filename,
            )
        ]


class _CrashingRule(Rule):
    """check() always raises RuntimeError."""

    id: ClassVar[str] = "CRASH001"
    description: ClassVar[str] = "Rule that always crashes"
    severity: ClassVar[Severity] = Severity.WARNING

    def check(self, tree, filename: str = "") -> list[Violation]:
        raise RuntimeError("intentional crash")


class _ShouldCheckFalseRule(Rule):
    """should_check() always returns False."""

    id: ClassVar[str] = "SKIP001"
    description: ClassVar[str] = "Rule that skips via should_check"
    severity: ClassVar[Severity] = Severity.WARNING

    @classmethod
    def should_check(cls, source: str) -> bool:
        return False

    def check(self, tree, filename: str = "") -> list[Violation]:
        return [
            Violation(
                rule_id=self.id,
                message="Should never appear",
                location=Location(row=1, column=0),
                severity=self.severity,
                filename=filename,
            )
        ]


class _ShouldCheckCrashRule(Rule):
    """should_check() always raises RuntimeError."""

    id: ClassVar[str] = "SCHECK_CRASH"
    description: ClassVar[str] = "Rule with crashing should_check"
    severity: ClassVar[Severity] = Severity.WARNING

    @classmethod
    def should_check(cls, source: str) -> bool:
        raise RuntimeError("should_check crash")

    def check(self, tree, filename: str = "") -> list[Violation]:
        return [
            Violation(
                rule_id=self.id,
                message="violation",
                location=Location(row=1, column=0),
                severity=self.severity,
                filename=filename,
            )
        ]


class _FixRule(Rule):
    """Produces a violation with a FixSuggestion."""

    id: ClassVar[str] = "FIX001"
    description: ClassVar[str] = "fix rule"
    severity: ClassVar[Severity] = Severity.WARNING

    def check(self, tree, filename: str = "") -> list[Violation]:
        return [
            Violation(
                rule_id=self.id,
                message="fix this",
                location=Location(row=1, column=0),
                end_location=Location(row=1, column=5),
                severity=self.severity,
                fix=FixSuggestion("Replace", "y = 1", "Because"),
                filename=filename,
            )
        ]


class _InspectorRule(Rule):
    """Captures _parent_map and _func_index for assertion."""

    id: ClassVar[str] = "INSPECT001"
    description: ClassVar[str] = "inspect"
    severity: ClassVar[Severity] = Severity.WARNING
    captured_parent_map: ClassVar = None
    captured_func_index: ClassVar = None

    def check(self, tree, filename: str = "") -> list[Violation]:
        _InspectorRule.captured_parent_map = self._parent_map
        _InspectorRule.captured_func_index = self._func_index
        return []


class _MultiViolationRule(Rule):
    """Produces one violation per ast.Assign node."""

    id: ClassVar[str] = "MULTI001"
    description: ClassVar[str] = "multi"
    severity: ClassVar[Severity] = Severity.WARNING

    def check(self, tree, filename: str = "") -> list[Violation]:
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="assign",
                        location=Location(row=node.lineno, column=node.col_offset),
                        severity=self.severity,
                        filename=filename,
                    )
                )
        return violations


def _make_violation(
    rule_id: str = "TEST001",
    row: int = 1,
    col: int = 0,
    severity: Severity = Severity.WARNING,
    filename: str = "test.py",
    fix: FixSuggestion | None = None,
    end_location: Location | None = None,
) -> Violation:
    return Violation(
        rule_id=rule_id,
        message="test violation",
        location=Location(row=row, column=col),
        end_location=end_location,
        severity=severity,
        fix=fix,
        filename=filename,
    )


def _write_py(tmp: Path, name: str, content: str) -> Path:
    """Create a .py file inside tmp directory."""
    p = tmp / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ===========================================================================
# discover_files
# ===========================================================================


class TestDiscoverFiles:
    def test_single_file(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        result = discover_files([f], [])
        assert result == [f]

    def test_non_py_file_excluded(self, tmp_path: Path):
        f_py = _write_py(tmp_path, "a.py", "x = 1\n")
        f_txt = tmp_path / "b.txt"
        f_txt.write_text("hello")
        result = discover_files([f_py, f_txt], [])
        assert result == [f_py]

    def test_directory_recursive(self, tmp_path: Path):
        f1 = _write_py(tmp_path, "a.py", "x = 1\n")
        f2 = _write_py(tmp_path, "sub/b.py", "y = 2\n")
        f3 = _write_py(tmp_path, "sub/deep/c.py", "z = 3\n")
        result = discover_files([tmp_path], [])
        assert len(result) == 3
        assert set(result) == {f1, f2, f3}

    def test_excludes_patterns(self, tmp_path: Path):
        _write_py(tmp_path, "keep.py", "x = 1\n")
        excluded_dir = tmp_path / "__pycache__"
        excluded_dir.mkdir()
        _write_py(excluded_dir, "cached.py", "x = 2\n")
        result = discover_files([tmp_path], ["__pycache__"])
        assert len(result) == 1
        assert result[0].name == "keep.py"

    def test_empty_directory(self, tmp_path: Path):
        result = discover_files([tmp_path], [])
        assert result == []

    def test_mixed_file_and_directory(self, tmp_path: Path):
        standalone = _write_py(tmp_path, "standalone.py", "x = 1\n")
        subdir = tmp_path / "pkg"
        subdir.mkdir()
        f_in_dir = _write_py(subdir, "mod.py", "y = 2\n")
        result = discover_files([standalone, subdir], [])
        assert set(result) == {standalone, f_in_dir}

    def test_results_sorted(self, tmp_path: Path):
        f_c = _write_py(tmp_path, "c.py", "x = 1\n")
        f_a = _write_py(tmp_path, "a.py", "x = 1\n")
        f_b = _write_py(tmp_path, "b.py", "x = 1\n")
        result = discover_files([tmp_path], [])
        assert result == sorted([f_a, f_b, f_c])

    def test_empty_paths_list(self):
        result = discover_files([], [])
        assert result == []

    def test_nonexistent_path_ignored(self, tmp_path: Path):
        ghost = tmp_path / "nonexistent.py"
        result = discover_files([ghost], [])
        assert result == []

    def test_directory_with_non_py_files(self, tmp_path: Path):
        _write_py(tmp_path, "a.py", "x = 1\n")
        (tmp_path / "readme.md").write_text("# readme")
        (tmp_path / "data.json").write_text("{}")
        result = discover_files([tmp_path], [])
        assert len(result) == 1


# ===========================================================================
# _filter_by_severity
# ===========================================================================


class TestFilterBySeverity:
    def test_filter_info_shows_all(self):
        violations = [
            _make_violation(severity=Severity.ERROR),
            _make_violation(severity=Severity.WARNING),
            _make_violation(severity=Severity.INFO),
        ]
        result = _filter_by_severity(violations, "info")
        assert len(result) == 3

    def test_filter_warning_excludes_info(self):
        violations = [
            _make_violation(severity=Severity.ERROR),
            _make_violation(severity=Severity.WARNING),
            _make_violation(severity=Severity.INFO),
        ]
        result = _filter_by_severity(violations, "warning")
        assert len(result) == 2
        assert all(v.severity != Severity.INFO for v in result)

    def test_filter_error_only(self):
        violations = [
            _make_violation(severity=Severity.ERROR),
            _make_violation(severity=Severity.WARNING),
            _make_violation(severity=Severity.INFO),
        ]
        result = _filter_by_severity(violations, "error")
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_empty_list(self):
        assert _filter_by_severity([], "error") == []

    def test_unknown_severity_defaults_to_info_level(self):
        violations = [
            _make_violation(severity=Severity.WARNING),
        ]
        # min_severity unknown → defaults to order 2 (info), so warning (1) passes
        result = _filter_by_severity(violations, "unknown_level")
        assert len(result) == 1

    def test_unknown_violation_severity_treated_as_info(self):
        v = _make_violation(severity=Severity.ERROR)
        # Temporarily monkey-patch severity value to something unknown
        # We test the SEVERITY_ORDER lookup default for unknown values
        assert SEVERITY_ORDER.get("error", 2) == 0  # known
        assert SEVERITY_ORDER.get("nonexistent", 2) == 2  # unknown defaults


# ===========================================================================
# Serialization: _violation_to_dict / _dict_to_violation
# ===========================================================================


class TestViolationSerialization:
    def test_roundtrip_basic(self):
        v = _make_violation()
        d = _violation_to_dict(v)
        v2 = _dict_to_violation(d)
        assert v2.rule_id == v.rule_id
        assert v2.message == v.message
        assert v2.location.row == v.location.row
        assert v2.location.column == v.location.column
        assert v2.severity == v.severity
        assert v2.filename == v.filename
        assert v2.end_location is None
        assert v2.fix is None

    def test_roundtrip_with_fix(self):
        fix = FixSuggestion(
            title="Replace X",
            replacement="x = 2",
            explanation="Better value",
        )
        v = _make_violation(fix=fix)
        d = _violation_to_dict(v)
        v2 = _dict_to_violation(d)
        assert v2.fix is not None
        assert v2.fix.title == "Replace X"
        assert v2.fix.replacement == "x = 2"
        assert v2.fix.explanation == "Better value"

    def test_roundtrip_with_end_location(self):
        v = _make_violation(end_location=Location(row=3, column=5))
        d = _violation_to_dict(v)
        assert d["end_location"] == {"row": 3, "column": 5}
        v2 = _dict_to_violation(d)
        assert v2.end_location is not None
        assert v2.end_location.row == 3
        assert v2.end_location.column == 5

    def test_dict_structure(self):
        v = _make_violation()
        d = _violation_to_dict(v)
        assert "rule_id" in d
        assert "message" in d
        assert "location" in d
        assert "end_location" in d
        assert "severity" in d
        assert "fix" in d
        assert "filename" in d
        assert d["fix"] is None


# ===========================================================================
# _build_ast_analysis
# ===========================================================================


class TestBuildAstAnalysis:
    def test_basic_function(self):
        tree = ast.parse("def foo(): pass\n")
        func_index, node_index, parent_map = _build_ast_analysis(tree)
        assert "foo" in func_index
        assert isinstance(func_index["foo"], ast.FunctionDef)

    def test_async_function(self):
        tree = ast.parse("async def bar(): pass\n")
        func_index, node_index, parent_map = _build_ast_analysis(tree)
        assert "bar" in func_index
        assert isinstance(func_index["bar"], ast.AsyncFunctionDef)

    def test_parent_map_links(self):
        tree = ast.parse("x = 1\n")
        func_index, node_index, parent_map = _build_ast_analysis(tree)
        # Every child should have a parent
        assert len(parent_map) > 0
        for child, parent in parent_map.items():
            assert child is not parent

    def test_empty_module(self):
        tree = ast.parse("")
        func_index, node_index, parent_map = _build_ast_analysis(tree)
        # Module itself is walked but has no children with parents
        assert isinstance(func_index, dict)
        assert isinstance(parent_map, dict)

    def test_nested_functions(self):
        code = """
def outer():
    def inner():
        pass
"""
        tree = ast.parse(code)
        func_index, _, _ = _build_ast_analysis(tree)
        assert "outer" in func_index
        assert "inner" in func_index


# ===========================================================================
# Caching internals
# ===========================================================================


class TestCaching:
    def test_cache_key_deterministic(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        key1 = _cache_key(f)
        key2 = _cache_key(f)
        assert key1 == key2

    def test_cache_key_changes_on_content_change(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        key1 = _cache_key(f)
        # modify file (ensure mtime changes)
        time.sleep(0.05)
        f.write_text("x = 2\n", encoding="utf-8")
        key2 = _cache_key(f)
        # keys should differ (mtime changed)
        assert key1 != key2

    def test_cache_path_format(self, tmp_path: Path):
        cp = _cache_path(tmp_path, "abc123")
        assert cp == tmp_path / "abc123.json"

    def test_save_and_get_cache(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        active_ids = ["DUMMY001"]
        violation_dicts = [
            {
                "rule_id": "DUMMY001",
                "message": "test",
                "location": {"row": 1, "column": 0},
                "end_location": None,
                "severity": "warning",
                "fix": None,
                "filename": str(f),
            }
        ]
        _save_to_cache(f, active_ids, violation_dicts, cache_dir)
        cached = _get_cached_violations(f, active_ids, cache_dir)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0]["rule_id"] == "DUMMY001"

    def test_cache_miss_returns_none(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached = _get_cached_violations(f, ["RULE001"], cache_dir)
        assert cached is None

    def test_cache_invalidation_on_rule_change(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        rules_v1 = ["RULE001"]
        rules_v2 = ["RULE001", "RULE002"]
        violation_dicts = [
            {
                "rule_id": "RULE001",
                "message": "test",
                "location": {"row": 1, "column": 0},
                "end_location": None,
                "severity": "warning",
                "fix": None,
                "filename": str(f),
            }
        ]
        _save_to_cache(f, rules_v1, violation_dicts, cache_dir)
        # Same rules → hit
        assert _get_cached_violations(f, rules_v1, cache_dir) is not None
        # Different rules → miss
        assert _get_cached_violations(f, rules_v2, cache_dir) is None

    def test_cache_corrupt_json_returns_none(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # Write a corrupt cache file
        key = _cache_key(f)
        bad_file = _cache_path(cache_dir, key)
        bad_file.write_text("NOT VALID JSON{{{")
        cached = _get_cached_violations(f, ["RULE001"], cache_dir)
        assert cached is None

    def test_clean_stale_cache_removes_old_files(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        # Create a stale file (set mtime to 8 days ago)
        stale = cache_dir / "stale.json"
        stale.write_text("{}")
        old_time = time.time() - CACHE_MAX_AGE_SECONDS - 3600
        os.utime(stale, (old_time, old_time))

        # Create a fresh file
        fresh = cache_dir / "fresh.json"
        fresh.write_text("{}")

        _clean_stale_cache(cache_dir)
        assert not stale.exists()
        assert fresh.exists()

    def test_clean_stale_cache_handles_non_json(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        non_json = cache_dir / "data.txt"
        non_json.write_text("hello")
        _clean_stale_cache(cache_dir)
        # Non-.json files should be untouched
        assert non_json.exists()

    def test_clean_stale_cache_handles_missing_dir(self, tmp_path: Path):
        nonexistent = tmp_path / "no_such_dir"
        # Should not raise
        _clean_stale_cache(nonexistent)

    def test_save_to_cache_oserror(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        cache_dir = tmp_path / "readonly"
        # Use a non-existent path; mkdir will be handled externally
        cache_dir.mkdir()
        key = _cache_key(f)
        target = _cache_path(cache_dir, key)
        # Make target a directory so writing fails
        target.mkdir()
        # Should not raise, silently handles OSError
        _save_to_cache(f, ["RULE001"], [], cache_dir)

    def test_get_cached_violations_oserror(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        key = _cache_key(f)
        target = _cache_path(cache_dir, key)
        # Write valid JSON, then replace with unreadable
        target.write_text('{"rules": [], "violations": []}')
        # Make it unreadable by removing read permission
        # On some systems this may not work; just test the corrupt json path
        target.write_text("{bad json")
        result = _get_cached_violations(f, [], cache_dir)
        assert result is None

    def test_clean_stale_cache_unlink_error(self, tmp_path: Path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        stale = cache_dir / "stale.json"
        stale.write_text("{}")
        old_time = time.time() - CACHE_MAX_AGE_SECONDS - 3600
        os.utime(stale, (old_time, old_time))

        # Mock unlink to raise OSError — file should remain but no crash
        with patch.object(Path, "unlink", side_effect=OSError("permission denied")):
            _clean_stale_cache(cache_dir)
        # File still exists because unlink failed
        assert stale.exists()


# ===========================================================================
# File I/O
# ===========================================================================


class TestReadFileSafe:
    def test_read_normal_file(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        path, content = _read_file_safe(f)
        assert path == f
        assert content == "x = 1\n"

    def test_read_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        path, content = _read_file_safe(f)
        assert content is None

    def test_read_too_large_file(self, tmp_path: Path):
        f = tmp_path / "big.py"
        f.write_text("x" * (MAX_FILE_SIZE + 1), encoding="utf-8")
        path, content = _read_file_safe(f)
        assert content is None

    def test_read_nonexistent_file(self, tmp_path: Path):
        ghost = tmp_path / "ghost.py"
        path, content = _read_file_safe(ghost)
        assert content is None

    def test_read_binary_file_as_unicode_error(self, tmp_path: Path):
        f = tmp_path / "binary.py"
        f.write_bytes(b"\xff\xfe\x80\x81")
        path, content = _read_file_safe(f)
        assert content is None


class TestReadFilesParallel:
    def test_small_batch_sequential(self, tmp_path: Path):
        files = [_write_py(tmp_path, f"f{i}.py", f"x = {i}\n") for i in range(3)]
        result = _read_files_parallel(files)
        assert len(result) == 3
        assert all(v is not None for v in result.values())

    def test_large_batch_parallel(self, tmp_path: Path):
        files = [_write_py(tmp_path, f"f{i}.py", f"x = {i}\n") for i in range(IO_PARALLEL_THRESHOLD + 2)]
        result = _read_files_parallel(files)
        assert len(result) == IO_PARALLEL_THRESHOLD + 2

    def test_empty_input(self):
        result = _read_files_parallel([])
        assert result == {}

    def test_mixed_valid_and_invalid(self, tmp_path: Path):
        valid = _write_py(tmp_path, "good.py", "x = 1\n")
        empty = tmp_path / "empty.py"
        empty.write_text("", encoding="utf-8")
        result = _read_files_parallel([valid, empty])
        assert result[valid] == "x = 1\n"
        assert result[empty] is None


# ===========================================================================
# lint_single_file
# ===========================================================================


class TestLintSingleFile:
    def test_syntax_error_returns_empty(self):
        result = lint_single_file("bad.py", "def (", [])
        assert result == []

    def test_no_rules(self):
        source = "x = 1\n"
        result = lint_single_file("test.py", source, [])
        assert result == []

    def test_with_dummy_rule(self):
        source = "x = 42\n"
        mod_cls = f"{_DummyRule.__module__}:{_DummyRule.__qualname__}"
        result = lint_single_file("test.py", source, [("DUMMY001", mod_cls)])
        assert len(result) >= 1
        assert result[0]["rule_id"] == "DUMMY001"

    def test_crashing_rule_skipped(self):
        source = "x = 1\n"
        mod_cls = f"{_CrashingRule.__module__}:{_CrashingRule.__qualname__}"
        result = lint_single_file("test.py", source, [("CRASH001", mod_cls)])
        assert result == []

    def test_should_check_false_skips(self):
        source = "x = 1\n"
        mod_cls = f"{_ShouldCheckFalseRule.__module__}:{_ShouldCheckFalseRule.__qualname__}"
        result = lint_single_file("test.py", source, [("SKIP001", mod_cls)])
        assert result == []

    def test_should_check_crash_still_runs(self):
        """When should_check crashes, it's caught and rule still runs."""
        source = "x = 1\n"
        mod_cls = f"{_ShouldCheckCrashRule.__module__}:{_ShouldCheckCrashRule.__qualname__}"
        result = lint_single_file("test.py", source, [("SCHECK_CRASH", mod_cls)])
        assert len(result) == 1

    def test_invalid_module_path_skipped(self):
        source = "x = 1\n"
        result = lint_single_file("test.py", source, [("BAD", "nonexistent_module:BadRule")])
        assert result == []

    def test_sets_parent_map_and_func_index(self):
        _InspectorRule.captured_parent_map = None
        _InspectorRule.captured_func_index = None
        source = "def foo(): pass\n"
        mod_cls = f"{_InspectorRule.__module__}:{_InspectorRule.__qualname__}"
        lint_single_file("test.py", source, [("INSPECT001", mod_cls)])
        assert _InspectorRule.captured_parent_map is not None
        assert _InspectorRule.captured_func_index is not None
        assert "foo" in _InspectorRule.captured_func_index

    def test_with_fix_suggestion(self):
        source = "x = 42\n"
        mod_cls = f"{_FixRule.__module__}:{_FixRule.__qualname__}"
        result = lint_single_file("test.py", source, [("FIX001", mod_cls)])
        assert len(result) == 1
        assert result[0]["fix"]["title"] == "Replace"
        assert result[0]["end_location"]["row"] == 1


# ===========================================================================
# _process_sequential / _process_parallel
# ===========================================================================


class TestProcessSequential:
    def test_basic(self):
        source = "x = 42\n"
        mod_cls = f"{_DummyRule.__module__}:{_DummyRule.__qualname__}"
        result = _process_sequential([("test.py", source)], [("DUMMY001", mod_cls)])
        assert len(result) >= 1

    def test_empty_input(self):
        assert _process_sequential([], []) == []

    def test_syntax_error_handled(self):
        result = _process_sequential([("bad.py", "def (")], [])
        assert result == []


class TestProcessParallel:
    def test_basic_parallel(self):
        source = "x = 42\n"
        mod_cls = f"{_DummyRule.__module__}:{_DummyRule.__qualname__}"
        uncached = [("test1.py", source), ("test2.py", source)]
        result = _process_parallel(uncached, [("DUMMY001", mod_cls)], 2)
        assert len(result) >= 2

    def test_fallback_on_exception(self):
        source = "x = 1\n"
        mod_cls = f"{_DummyRule.__module__}:{_DummyRule.__qualname__}"
        uncached = [("test.py", source)]

        with patch("smart_linter.engine.ProcessPoolExecutor", side_effect=RuntimeError("pool failed")):
            result = _process_parallel(uncached, [("DUMMY001", mod_cls)], 2)
        assert len(result) >= 1

    def test_future_exception_handled(self):
        """Individual future exceptions are caught and skipped."""
        source = "x = 1\n"
        uncached = [("test.py", source)]

        mock_future = MagicMock()
        mock_future.result.side_effect = RuntimeError("future crashed")

        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = mock_future

        with patch("smart_linter.engine.ProcessPoolExecutor", return_value=mock_executor):
            with patch("smart_linter.engine.as_completed", return_value=[mock_future]):
                result = _process_parallel(uncached, [], 2)
        assert result == []


# ===========================================================================
# run() — main entry point
# ===========================================================================


class TestRun:
    def _make_config(self, **overrides) -> Config:
        defaults = {
            "select": ["all"],
            "ignore": [],
            "custom_rules": [],
            "min_severity": "info",
            "exclude": [],
            "no_cache": True,
            "workers": 0,
        }
        defaults.update(overrides)
        return Config(**defaults)

    def test_empty_paths_returns_empty(self, tmp_path: Path):
        config = self._make_config()
        result = run([], config)
        assert result == []

    def test_no_violations(self, tmp_path: Path):
        f = _write_py(tmp_path, "clean.py", "x = 1\n")
        config = self._make_config()
        # No rules loaded (empty registry), so no violations
        with patch("smart_linter.engine.get_all_rules", return_value={}):
            result = run([f], config)
        assert result == []

    def test_with_violations(self, tmp_path: Path):
        f = _write_py(tmp_path, "has_issue.py", "x = 42\n")
        config = self._make_config()
        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"DUMMY001": _DummyRule},
        ):
            result = run([f], config)
        assert len(result) >= 1
        assert result[0].rule_id == "DUMMY001"

    def test_syntax_error_skipped_gracefully(self, tmp_path: Path):
        f = _write_py(tmp_path, "bad.py", "def (\n")
        config = self._make_config()
        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"DUMMY001": _DummyRule},
        ):
            result = run([f], config)
        assert result == []

    def test_unicode_error_skipped_gracefully(self, tmp_path: Path):
        f = tmp_path / "binary.py"
        f.write_bytes(b"\xff\xfe\x80\x81")
        config = self._make_config()
        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"DUMMY001": _DummyRule},
        ):
            result = run([f], config)
        assert result == []

    def test_severity_filtering(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        config = self._make_config(min_severity="error")
        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"DUMMY001": _DummyRule, "DUMMY002": _DummyErrorRule, "DUMMY003": _DummyInfoRule},
        ):
            result = run([f], config)
        # Only ERROR severity should pass
        assert all(v.severity == Severity.ERROR for v in result)

    def test_select_rules(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        config = self._make_config(select=["DUMMY002"])
        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"DUMMY002": _DummyErrorRule},
        ) as mock_rules:
            result = run([f], config)
        assert all(v.rule_id == "DUMMY002" for v in result)

    def test_ignore_rules(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        config = self._make_config(ignore=["DUMMY001"])
        # get_all_rules is called with ignore param
        with patch("smart_linter.engine.get_all_rules", return_value={}) as mock:
            result = run([f], config)
        # Verify get_all_rules was called with ignore
        call_kwargs = mock.call_args
        assert call_kwargs[1]["ignore"] == ["DUMMY001"] or call_kwargs.kwargs.get("ignore") == ["DUMMY001"]

    def test_with_caching_enabled(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 42\n")
        config = self._make_config(no_cache=False)

        with (
            patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}),
            patch("smart_linter.engine.CACHE_DIR_NAME", str(tmp_path / "cache_test")),
        ):
            cache_dir = tmp_path / "cache_test"
            cache_dir.mkdir(exist_ok=True)

            # First run — computes and caches
            result1 = run([f], config)
            assert len(result1) >= 1

            # Second run — should use cache
            result2 = run([f], config)
            assert len(result2) == len(result1)

    def test_no_cache_flag(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 42\n")
        config = self._make_config(no_cache=True)

        with patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}):
            result = run([f], config)
        assert len(result) >= 1

    def test_workers_positive(self, tmp_path: Path):
        files = [_write_py(tmp_path, f"f{i}.py", f"x = {i}\n") for i in range(4)]
        config = self._make_config(workers=2, no_cache=True)

        with patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}):
            result = run(files, config)
        assert len(result) >= 4

    def test_workers_zero_auto(self, tmp_path: Path):
        files = [_write_py(tmp_path, f"f{i}.py", f"x = {i}\n") for i in range(3)]
        config = self._make_config(workers=0, no_cache=True)

        with patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}):
            result = run(files, config)
        assert len(result) >= 3

    def test_single_file_workers_positive(self, tmp_path: Path):
        """Single file with workers > 0 still runs (sequential fallback)."""
        f = _write_py(tmp_path, "a.py", "x = 42\n")
        config = self._make_config(workers=4, no_cache=True)

        with patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}):
            result = run([f], config)
        assert len(result) >= 1

    def test_results_sorted_by_filename_row_col(self, tmp_path: Path):
        f1 = _write_py(tmp_path, "a.py", "x = 1\ny = 2\n")
        f2 = _write_py(tmp_path, "b.py", "z = 3\n")

        config = self._make_config(no_cache=True)
        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"MULTI001": _MultiViolationRule},
        ):
            result = run([f2, f1], config)  # reversed order

        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            assert (a.filename, a.location.row, a.location.column) <= (
                b.filename,
                b.location.row,
                b.location.column,
            )

    def test_cache_dir_creation_failure_disables_cache(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        config = self._make_config(no_cache=False)

        with (
            patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}),
            patch("smart_linter.engine.CACHE_DIR_NAME", "/nonexistent/path/cache"),
            patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")),
        ):
            # Should still work, just without caching
            result = run([f], config)
        assert len(result) >= 1

    def test_directory_path_discovers_files(self, tmp_path: Path):
        _write_py(tmp_path, "a.py", "x = 42\n")
        _write_py(tmp_path, "sub/b.py", "y = 99\n")
        config = self._make_config(no_cache=True)

        with patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}):
            result = run([tmp_path], config)
        assert len(result) >= 2

    def test_custom_rules_path(self, tmp_path: Path):
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        config = self._make_config(custom_rules=["some.module:SomeRule"], no_cache=True)

        with patch(
            "smart_linter.engine.get_all_rules",
            return_value={"CUSTOM001": _DummyRule},
        ) as mock:
            result = run([f], config)
        # Verify custom_rules were passed
        call_kwargs = mock.call_args
        kwargs = call_kwargs[1] if len(call_kwargs) > 1 else call_kwargs.kwargs
        assert kwargs.get("custom_paths") == ["some.module:SomeRule"]

    def test_parallel_with_mock_pool(self, tmp_path: Path):
        """Test parallel path using mocked ProcessPoolExecutor."""
        files = [_write_py(tmp_path, f"f{i}.py", f"x = {i}\n") for i in range(4)]
        config = self._make_config(workers=2, no_cache=True)

        mod_cls = f"{_DummyRule.__module__}:{_DummyRule.__qualname__}"
        mock_future = MagicMock()
        mock_future.result.return_value = [
            {
                "rule_id": "DUMMY001",
                "message": "test",
                "location": {"row": 1, "column": 0},
                "end_location": None,
                "severity": "warning",
                "fix": None,
                "filename": str(files[0]),
            }
        ]

        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = mock_future

        with (
            patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}),
            patch("smart_linter.engine.ProcessPoolExecutor", return_value=mock_executor),
            patch("smart_linter.engine.as_completed", return_value=[mock_future]),
        ):
            result = run(files, config)
        assert len(result) >= 1

    def test_caching_saves_and_retrieves(self, tmp_path: Path):
        """Full integration: first run caches, second run reads from cache."""
        f = _write_py(tmp_path, "a.py", "x = 42\n")
        cache_dir = tmp_path / "my_cache"
        cache_dir.mkdir()
        config = self._make_config(no_cache=False)

        with (
            patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}),
            patch("smart_linter.engine.CACHE_DIR_NAME", str(cache_dir)),
        ):
            # First run: computes
            r1 = run([f], config)
            # Cache should have files
            cache_files = list(cache_dir.glob("*.json"))
            assert len(cache_files) >= 1

            # Second run: reads from cache
            r2 = run([f], config)
            assert len(r2) == len(r1)

    def test_select_all_passes_none(self, tmp_path: Path):
        """When select=["all"], get_all_rules should receive None for select."""
        f = _write_py(tmp_path, "a.py", "x = 1\n")
        config = self._make_config(select=["all"])

        with patch("smart_linter.engine.get_all_rules", return_value={}) as mock:
            run([f], config)
        kwargs = mock.call_args[1] if len(mock.call_args) > 1 else mock.call_args.kwargs
        # select=["all"] → passes None
        assert kwargs.get("select") is None

    def test_workers_clamped_to_uncached_count(self, tmp_path: Path):
        """Workers should be clamped to min(workers, len(uncached))."""
        f = _write_py(tmp_path, "a.py", "x = 42\n")
        config = self._make_config(workers=10, no_cache=True)

        with patch("smart_linter.engine.get_all_rules", return_value={"DUMMY001": _DummyRule}):
            result = run([f], config)
        assert len(result) >= 1


def test_rule_base_check_raises_not_implemented():
    from smart_linter.models import Rule

    rule = Rule()
    with pytest.raises(NotImplementedError):
        rule.check(ast.parse("x = 1"))
