"""Rule registry with auto-discovery via entry_points and custom paths."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from smart_linter.models import Rule

_BUILTIN_RULES: dict[str, type[Rule]] = {}
_REGISTERED_RULES: dict[str, type[Rule]] = {}


def register(cls: type[Rule]) -> type[Rule]:
    """Decorator to register a rule class for auto-discovery."""
    _REGISTERED_RULES[cls.id] = cls
    return cls


def _discover_builtin_rules() -> dict[str, type[Rule]]:
    from smart_linter.models import Rule

    rules: dict[str, type[Rule]] = {}
    rules_dir = Path(__file__).parent / "rules"
    for py_file in sorted(rules_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        module_name = f"smart_linter.rules.{py_file.stem}"
        try:
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Rule)
                    and attr is not Rule
                    and hasattr(attr, "id")
                    and hasattr(attr, "check")
                ):
                    rules[attr.id] = attr
        except Exception:
            continue
    return rules


def _discover_entry_points() -> dict[str, type[Rule]]:
    rules: dict[str, type[Rule]] = {}
    try:
        from importlib.metadata import entry_points

        eps = entry_points(group="smart_linter.rules")
    except Exception:
        return rules

    for ep in eps:
        try:
            obj = ep.load()
            if isinstance(obj, type) and hasattr(obj, "id"):
                rules[obj.id] = obj
        except Exception:
            continue
    return rules


def _load_custom_rule(path: str) -> type[Rule] | None:
    try:
        if ":" in path:
            module_path, class_name = path.rsplit(":", 1)
        else:
            module_path = path
            class_name = None

        module = importlib.import_module(module_path)
        if class_name:
            return getattr(module, class_name, None)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and hasattr(attr, "id")
                and hasattr(attr, "check")
                and attr_name.endswith("Rule")
            ):
                return attr
    except Exception:
        pass
    return None


def get_all_rules(
    custom_paths: list[str] | None = None,
    select: list[str] | None = None,
    ignore: list[str] | None = None,
) -> dict[str, type[Rule]]:
    all_rules: dict[str, type[Rule]] = {}
    all_rules.update(_discover_builtin_rules())
    all_rules.update(_REGISTERED_RULES)
    all_rules.update(_discover_entry_points())

    if custom_paths:
        for path in custom_paths:
            rule_cls = _load_custom_rule(path)
            if rule_cls:
                all_rules[rule_cls.id] = rule_cls

    if select and "all" not in select:
        all_rules = {k: v for k, v in all_rules.items() if k in select}

    if ignore:
        all_rules = {k: v for k, v in all_rules.items() if k not in ignore}

    return all_rules
