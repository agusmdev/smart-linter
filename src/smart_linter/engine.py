"""Core linting engine: file discovery, AST parsing, rule dispatch."""

from __future__ import annotations

import ast
from pathlib import Path

from smart_linter.config import Config
from smart_linter.models import Rule, Violation
from smart_linter.registry import get_all_rules

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def discover_files(paths: list[Path], exclude: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            for py_file in path.rglob("*.py"):
                rel = str(py_file)
                if not any(exc in rel for exc in exclude):
                    files.append(py_file)
    return sorted(files)


def _filter_by_severity(
    violations: list[Violation], min_severity: str
) -> list[Violation]:
    min_order = SEVERITY_ORDER.get(min_severity, 2)
    return [
        v for v in violations if SEVERITY_ORDER.get(v.severity.value, 2) <= min_order
    ]


def run(
    paths: list[Path],
    config: Config,
) -> list[Violation]:
    rule_classes = get_all_rules(
        custom_paths=config.custom_rules or None,
        select=config.select if config.select != ["all"] else None,
        ignore=config.ignore or None,
    )

    files = discover_files(paths, config.exclude)

    all_violations: list[Violation] = []

    for filepath in files:
        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(filepath))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for rule_cls in rule_classes.values():
            rule = rule_cls()
            violations = rule.check(tree, filename=str(filepath))
            all_violations.extend(violations)

    all_violations = _filter_by_severity(all_violations, config.min_severity)
    all_violations.sort(key=lambda v: (v.filename, v.location.row, v.location.column))

    return all_violations
