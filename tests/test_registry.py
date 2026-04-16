"""Tests for smart_linter.registry."""

from __future__ import annotations

import importlib
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from smart_linter.models import Rule, Severity, Violation, Location
from smart_linter.registry import (
    _discover_builtin_rules,
    _discover_entry_points,
    _load_custom_rule,
    get_all_rules,
    register,
)


class _StubRule(Rule):
    id: ClassVar[str] = "STUB001"
    description: ClassVar[str] = "A stub rule for testing"
    severity: ClassVar[Severity] = Severity.WARNING

    def check(self, tree, filename: str = "") -> list[Violation]:
        return []


class _AnotherStubRule(Rule):
    id: ClassVar[str] = "STUB002"
    description: ClassVar[str] = "Another stub rule"
    severity: ClassVar[Severity] = Severity.ERROR

    def check(self, tree, filename: str = "") -> list[Violation]:
        return []


# ---------------------------------------------------------------------------
# _discover_builtin_rules
# ---------------------------------------------------------------------------


class TestDiscoverBuiltinRules:
    def test_returns_dict(self):
        rules = _discover_builtin_rules()
        assert isinstance(rules, dict)

    def test_finds_rules_in_rules_package(self):
        rules = _discover_builtin_rules()
        rule_ids = set(rules.keys())
        assert "ASYNC001" in rule_ids
        assert "ERR001" in rule_ids

    def test_all_values_are_rule_subclasses(self):
        rules = _discover_builtin_rules()
        for rule_id, rule_cls in rules.items():
            assert issubclass(rule_cls, Rule)
            assert hasattr(rule_cls, "id")
            assert hasattr(rule_cls, "check")

    def test_skips_underscore_files(self):
        rules = _discover_builtin_rules()
        for rule_cls in rules.values():
            assert not rule_cls.id.startswith("_")

    def test_discovers_multiple_rules(self):
        rules = _discover_builtin_rules()
        assert len(rules) >= 5


# ---------------------------------------------------------------------------
# _discover_entry_points
# ---------------------------------------------------------------------------


class TestDiscoverEntryPoints:
    def test_returns_empty_when_no_entry_points(self):
        with patch("importlib.metadata.entry_points", side_effect=Exception("nope")):
            result = _discover_entry_points()
        assert isinstance(result, dict)
        assert len(result) == 0

    def test_loads_entry_point_rules(self):
        mock_ep = MagicMock()
        mock_ep.load.return_value = _StubRule
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            result = _discover_entry_points()
        assert "STUB001" in result
        assert result["STUB001"] is _StubRule

    def test_skips_entry_points_without_id(self):
        class NoIdRule:
            pass

        mock_ep = MagicMock()
        mock_ep.load.return_value = NoIdRule
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            result = _discover_entry_points()
        assert len(result) == 0

    def test_handles_load_exception(self):
        mock_ep = MagicMock()
        mock_ep.load.side_effect = ImportError("broken")
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            result = _discover_entry_points()
        assert len(result) == 0


# ---------------------------------------------------------------------------
# register decorator
# ---------------------------------------------------------------------------


class TestRegister:
    def test_registers_rule(self):
        import smart_linter.registry as reg

        original = dict(reg._REGISTERED_RULES)
        try:
            result = register(_StubRule)
            assert result is _StubRule
            assert "STUB001" in reg._REGISTERED_RULES
            assert reg._REGISTERED_RULES["STUB001"] is _StubRule
        finally:
            reg._REGISTERED_RULES.clear()
            reg._REGISTERED_RULES.update(original)

    def test_returns_class_unchanged(self):
        import smart_linter.registry as reg

        original = dict(reg._REGISTERED_RULES)
        try:
            result = register(_AnotherStubRule)
            assert result is _AnotherStubRule
        finally:
            reg._REGISTERED_RULES.clear()
            reg._REGISTERED_RULES.update(original)


# ---------------------------------------------------------------------------
# _load_custom_rule
# ---------------------------------------------------------------------------


class TestLoadCustomRule:
    def test_loads_rule_with_colon_path(self):
        with patch("smart_linter.registry.importlib") as mock_importlib:
            mock_module = MagicMock()
            mock_module.MyRule = _StubRule
            mock_importlib.import_module.return_value = mock_module
            result = _load_custom_rule("my_pkg.rules:MyRule")
        assert result is not None

    def test_loads_rule_auto_discover_by_suffix(self):
        with patch("smart_linter.registry.importlib") as mock_importlib:
            mock_module = MagicMock()
            mock_module.SomeRule = _StubRule
            mock_module.NotARule = "not a class"
            mock_importlib.import_module.return_value = mock_module
            result = _load_custom_rule("my_pkg.rules")
        assert result is not None

    def test_returns_none_on_import_error(self):
        with patch(
            "smart_linter.registry.importlib.import_module",
            side_effect=ImportError("nope"),
        ):
            result = _load_custom_rule("nonexistent.module:Rule")
        assert result is None

    def test_returns_none_on_invalid_path(self):
        result = _load_custom_rule("clearly_invalid_module_path_xyz:Rule")
        assert result is None


# ---------------------------------------------------------------------------
# get_all_rules
# ---------------------------------------------------------------------------


class TestGetAllRules:
    def test_returns_builtin_rules_by_default(self):
        rules = get_all_rules()
        assert "ASYNC001" in rules
        assert "ERR001" in rules

    def test_select_filters_rules(self):
        rules = get_all_rules(select=["ASYNC001"])
        assert "ASYNC001" in rules
        assert "ERR001" not in rules
        assert "SEC001" not in rules

    def test_select_all_returns_all(self):
        rules = get_all_rules(select=["all"])
        assert len(rules) >= 5

    def test_ignore_excludes_rules(self):
        rules = get_all_rules(ignore=["ASYNC001"])
        assert "ASYNC001" not in rules
        assert "ERR001" in rules

    def test_select_and_ignore_combined(self):
        rules = get_all_rules(select=["ASYNC001", "ERR001"], ignore=["ERR001"])
        assert "ASYNC001" in rules
        assert "ERR001" not in rules

    def test_custom_paths_loaded(self):
        with patch("smart_linter.registry._load_custom_rule", return_value=_StubRule):
            rules = get_all_rules(custom_paths=["stub:StubRule"])
        assert "STUB001" in rules

    def test_custom_paths_none_no_error(self):
        rules = get_all_rules(custom_paths=None)
        assert isinstance(rules, dict)

    def test_includes_registered_rules(self):
        import smart_linter.registry as reg

        original = dict(reg._REGISTERED_RULES)
        try:
            reg._REGISTERED_RULES["STUB001"] = _StubRule
            rules = get_all_rules()
            assert "STUB001" in rules
        finally:
            reg._REGISTERED_RULES.clear()
            reg._REGISTERED_RULES.update(original)

    def test_empty_select_returns_all(self):
        rules = get_all_rules(select=[])
        assert len(rules) >= 5

    def test_select_nonexistent_rule_returns_empty(self):
        rules = get_all_rules(select=["NONEXISTENT999"])
        assert len(rules) == 0

    def test_select_with_all_in_list_returns_all(self):
        rules = get_all_rules(select=["all", "ASYNC001"])
        assert len(rules) >= 5

    def test_custom_path_load_failure_skipped(self):
        with patch("smart_linter.registry._load_custom_rule", return_value=None):
            rules = get_all_rules(custom_paths=["broken:Rule"])
        assert "STUB001" not in rules


def test_discover_builtin_rules_handles_import_error():
    from smart_linter.registry import _discover_builtin_rules

    with patch("smart_linter.registry.importlib.import_module", side_effect=ImportError("broken")):
        rules = _discover_builtin_rules()
    assert isinstance(rules, dict)
