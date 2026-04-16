"""Core linting engine: file discovery, AST parsing, rule dispatch.

Performance optimizations:
- Parallel file I/O via ThreadPoolExecutor
- Parallel AST analysis via ProcessPoolExecutor
- Content-hash caching (mtime + size based)
- Single-pass AST pre-analysis (parent_map + func_index)
- Early-exit via Rule.should_check() string scan
- Slotted dataclasses for reduced memory overhead
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from smart_linter.config import Config
from smart_linter.models import FixSuggestion, Location, Severity, Violation
from smart_linter.registry import get_all_rules

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

CACHE_DIR_NAME = ".smart_linter_cache"
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
CACHE_MAX_AGE_SECONDS = 7 * 86400  # 7 days
IO_PARALLEL_THRESHOLD = 4


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


def _filter_by_severity(violations: list[Violation], min_severity: str) -> list[Violation]:
    min_order = SEVERITY_ORDER.get(min_severity, 2)
    return [v for v in violations if SEVERITY_ORDER.get(v.severity.value, 2) <= min_order]


# ---------------------------------------------------------------------------
# Violation serialization (for crossing process boundaries)
# ---------------------------------------------------------------------------


def _violation_to_dict(v: Violation) -> dict[str, Any]:
    d: dict[str, Any] = {
        "rule_id": v.rule_id,
        "message": v.message,
        "location": {"row": v.location.row, "column": v.location.column},
        "end_location": ({"row": v.end_location.row, "column": v.end_location.column} if v.end_location else None),
        "severity": v.severity.value,
        "fix": None,
        "filename": v.filename,
    }
    if v.fix:
        d["fix"] = {
            "title": v.fix.title,
            "replacement": v.fix.replacement,
            "explanation": v.fix.explanation,
        }
    return d


def _dict_to_violation(d: dict[str, Any]) -> Violation:
    return Violation(
        rule_id=d["rule_id"],
        message=d["message"],
        location=Location(row=d["location"]["row"], column=d["location"]["column"]),
        end_location=(
            Location(row=d["end_location"]["row"], column=d["end_location"]["column"]) if d["end_location"] else None
        ),
        severity=Severity(d["severity"]),
        fix=(
            FixSuggestion(
                title=d["fix"]["title"],
                replacement=d["fix"]["replacement"],
                explanation=d["fix"]["explanation"],
            )
            if d["fix"]
            else None
        ),
        filename=d["filename"],
    )


# ---------------------------------------------------------------------------
# Single-pass AST pre-analysis
# ---------------------------------------------------------------------------


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Build parent map lazily, only when a rule needs it."""
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


# Node types that rules actually look up in node_index.
# Only these are indexed; others are traversed but not stored.
_INDEXED_TYPES = frozenset({
    ast.Assign, ast.AugAssign, ast.Call, ast.ClassDef, ast.Try,
    ast.For, ast.AsyncFor, ast.While, ast.AsyncFunctionDef,
    ast.Module, ast.FunctionDef, ast.If, ast.Assert, ast.IfExp,
})


def _build_ast_analysis(
    tree: ast.AST,
) -> tuple[
    dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    dict[type, list[ast.AST]],
    dict[ast.AST, ast.AST],
]:
    """Single-pass analysis: func_index, node_type_index, and parent_map."""
    func_index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    node_index: dict[type, list[ast.AST]] = {}
    parent_map: dict[ast.AST, ast.AST] = {}
    stack = [tree]
    while stack:
        node = stack.pop()
        node_type = type(node)
        if node_type in _INDEXED_TYPES:
            if node_type not in node_index:
                node_index[node_type] = []
            node_index[node_type].append(node)
            if node_type is ast.FunctionDef or node_type is ast.AsyncFunctionDef:
                func_index[node.name] = node
        for field_name in node._fields:
            value = getattr(node, field_name, None)
            if value is None:
                continue
            if isinstance(value, ast.AST):
                parent_map[value] = node
                stack.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        parent_map[item] = node
                        stack.append(item)
    return func_index, node_index, parent_map


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def _cache_key(filepath: Path) -> str:
    stat = filepath.stat()
    raw = f"{filepath}:{stat.st_mtime_ns}:{stat.st_size}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def _get_cached_violations(
    filepath: Path,
    active_rule_ids: list[str],
    cache_dir: Path,
) -> list[dict[str, Any]] | None:
    key = _cache_key(filepath)
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("rules") != active_rule_ids:
        return None
    return data.get("violations", [])


def _save_to_cache(
    filepath: Path,
    active_rule_ids: list[str],
    violation_dicts: list[dict[str, Any]],
    cache_dir: Path,
) -> None:
    key = _cache_key(filepath)
    path = _cache_path(cache_dir, key)
    try:
        with open(path, "w") as f:
            json.dump({"rules": active_rule_ids, "violations": violation_dicts}, f)
    except OSError:
        pass


def _clean_stale_cache(cache_dir: Path) -> None:
    now = time.time()
    try:
        for entry in cache_dir.iterdir():
            if entry.is_file() and entry.suffix == ".json" and now - entry.stat().st_mtime > CACHE_MAX_AGE_SECONDS:
                with contextlib.suppress(OSError):
                    entry.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# File I/O (parallel reads via ThreadPoolExecutor)
# ---------------------------------------------------------------------------


def _read_file_safe(filepath: Path) -> tuple[Path, str | None]:
    try:
        size = filepath.stat().st_size
        if size > MAX_FILE_SIZE or size == 0:
            return filepath, None
        return filepath, filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return filepath, None


def _read_files_parallel(files: list[Path]) -> dict[Path, str | None]:
    if len(files) <= IO_PARALLEL_THRESHOLD:
        return dict(_read_file_safe(f) for f in files)
    with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 4, len(files))) as pool:
        return dict(pool.map(_read_file_safe, files))


# ---------------------------------------------------------------------------
# Worker function (module-level for pickling with ProcessPoolExecutor)
# ---------------------------------------------------------------------------


def lint_single_file(
    filepath_str: str,
    source: str,
    rule_module_paths: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source, filename=filepath_str)
    except SyntaxError:
        return []

    func_index, node_index, parent_map = _build_ast_analysis(tree)

    violations: list[Violation] = []

    for _rule_id, module_class_path in rule_module_paths:
        try:
            mod_name, cls_name = module_class_path.rsplit(":", 1)
            mod = importlib.import_module(mod_name)
            rule_cls = getattr(mod, cls_name)
        except Exception:
            continue

        if hasattr(rule_cls, "should_check"):
            try:
                if not rule_cls.should_check(source):
                    continue
            except Exception:
                pass

        rule = rule_cls()
        rule._parent_map = parent_map
        rule._func_index = func_index
        rule._node_index = node_index

        try:
            violations.extend(rule.check(tree, filename=filepath_str))
        except Exception:
            continue

    return [_violation_to_dict(v) for v in violations]


# ---------------------------------------------------------------------------
# Optimized sequential path (no IPC overhead, direct rule instances)
# ---------------------------------------------------------------------------


def _lint_sequential_optimized(
    uncached: list[tuple[str, str]],
    rule_classes: dict[str, type],
) -> list[dict[str, Any]]:
    """Lint files sequentially with pre-instantiated rules and shared analysis."""
    results: list[dict[str, Any]] = []

    for filepath_str, source in uncached:
        try:
            tree = ast.parse(source, filename=filepath_str)
        except SyntaxError:
            continue

        func_index, node_index, parent_map = _build_ast_analysis(tree)

        for rule_id, rule_cls in rule_classes.items():
            if hasattr(rule_cls, "should_check"):
                try:
                    if not rule_cls.should_check(source):
                        continue
                except Exception:
                    pass

            rule = rule_cls()
            rule._parent_map = parent_map
            rule._func_index = func_index
            rule._node_index = node_index

            try:
                violations = rule.check(tree, filename=filepath_str)
                results.extend(_violation_to_dict(v) for v in violations)
            except Exception:
                continue

    return results


# ---------------------------------------------------------------------------
# Parallel / sequential dispatch
# ---------------------------------------------------------------------------


def _process_parallel(
    uncached: list[tuple[str, str]],
    rule_info: list[tuple[str, str]],
    num_workers: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    try:
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(lint_single_file, fp, src, rule_info): fp for fp, src in uncached}
            for future in as_completed(futures):
                with contextlib.suppress(Exception):
                    results.extend(future.result())
    except Exception:
        return _process_sequential(uncached, rule_info)
    return results


def _process_sequential(
    uncached: list[tuple[str, str]],
    rule_info: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for filepath_str, source in uncached:
        results.extend(lint_single_file(filepath_str, source, rule_info))
    return results


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(paths: list[Path], config: Config) -> list[Violation]:
    rule_classes = get_all_rules(
        custom_paths=config.custom_rules or None,
        select=config.select if config.select != ["all"] else None,
        ignore=config.ignore or None,
    )

    files = discover_files(paths, config.exclude)
    if not files:
        return []

    active_rule_ids = sorted(rule_classes.keys())

    rule_info: list[tuple[str, str]] = [
        (rule_id, f"{cls.__module__}:{cls.__qualname__}") for rule_id, cls in rule_classes.items()
    ]

    cache_dir = Path(CACHE_DIR_NAME)
    use_cache = not config.no_cache
    if use_cache:
        try:
            cache_dir.mkdir(exist_ok=True)
            _clean_stale_cache(cache_dir)
        except OSError:
            use_cache = False

    file_data = _read_files_parallel(files)

    cached_violation_dicts: list[dict[str, Any]] = []
    uncached: list[tuple[str, str]] = []

    for filepath in files:
        source = file_data.get(filepath)
        if source is None:
            continue

        if use_cache:
            cached = _get_cached_violations(filepath, active_rule_ids, cache_dir)
            if cached is not None:
                cached_violation_dicts.extend(cached)
                continue

        uncached.append((str(filepath), source))

    new_violation_dicts: list[dict[str, Any]] = []

    if uncached:
        if config.workers > 0:
            num_workers = min(config.workers, len(uncached))
            new_violation_dicts = _process_parallel(uncached, rule_info, num_workers)
        else:
            new_violation_dicts = _lint_sequential_optimized(uncached, rule_classes)

        if use_cache and new_violation_dicts:
            by_file: dict[str, list[dict[str, Any]]] = {}
            for vd in new_violation_dicts:
                by_file.setdefault(vd["filename"], []).append(vd)
            for filepath_str, _source in uncached:
                _save_to_cache(
                    Path(filepath_str),
                    active_rule_ids,
                    by_file.get(filepath_str, []),
                    cache_dir,
                )

    all_dicts = cached_violation_dicts + new_violation_dicts

    all_violations = [_dict_to_violation(d) for d in all_dicts]
    all_violations = _filter_by_severity(all_violations, config.min_severity)
    all_violations.sort(key=lambda v: (v.filename, v.location.row, v.location.column))

    return all_violations
