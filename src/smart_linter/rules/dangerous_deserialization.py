"""SEC003: Detect dangerous deserialization that can execute arbitrary code."""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)

_DANGEROUS_CALLS: dict[str, dict[str, tuple[str, str, str]]] = {
    "pickle": {
        "loads": (
            "pickle",
            "Use json or msgpack for untrusted data",
            "pickle.loads() can execute arbitrary code during deserialization. "
            "Use json.loads() or msgpack for data from untrusted sources.",
        ),
        "load": (
            "pickle",
            "Use json or msgpack for untrusted data",
            "pickle.load() can execute arbitrary code during deserialization. "
            "Use json.load() or msgpack for data from untrusted sources.",
        ),
    },
    "marshal": {
        "loads": (
            "marshal",
            "Avoid marshal for untrusted data — use json instead",
            "marshal.loads() is not designed for untrusted data and can crash "
            "the interpreter. Use json.loads() for data from untrusted sources.",
        ),
        "load": (
            "marshal",
            "Avoid marshal for untrusted data — use json instead",
            "marshal.load() is not designed for untrusted data and can crash "
            "the interpreter. Use json.load() for data from untrusted sources.",
        ),
    },
    "shelve": {
        "open": (
            "shelve",
            "Avoid shelve for untrusted data — it uses pickle internally",
            "shelve.open() uses pickle internally, which can execute arbitrary "
            "code. Use a database like sqlite3 with json serialization instead.",
        ),
    },
    "jsonpickle": {
        "decode": (
            "jsonpickle",
            "Avoid jsonpickle.decode() for untrusted data — use json instead",
            "jsonpickle.decode() can reconstruct arbitrary Python objects, "
            "which is dangerous with untrusted input. Use json.loads() instead.",
        ),
    },
}

_YAML_MODULE_NAMES = frozenset({"yaml", "pyyaml"})

_SAFE_LOADERS: frozenset[str] = frozenset(
    {
        "SafeLoader",
        "BaseLoader",
        "CSafeLoader",
        "CLoader",
    }
)


def _get_call_info(node: ast.Call) -> tuple[str | None, str | None]:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None, None

    func_name = func.attr

    if isinstance(func.value, ast.Name):
        return func.value.id, func_name

    return None, None


def _get_loader_name(keyword: ast.keyword) -> str | None:
    value = keyword.value
    if isinstance(value, ast.Attribute):
        return value.attr
    if isinstance(value, ast.Name):
        return value.id
    return None


def _is_yaml_load_unsafe(node: ast.Call) -> bool:
    loader_kw = None
    for kw in node.keywords:
        if kw.arg == "Loader":
            loader_kw = kw
            break

    if loader_kw is None:
        return True

    loader_name = _get_loader_name(loader_kw)
    if loader_name is None:
        return True

    return loader_name not in _SAFE_LOADERS


class DangerousDeserializationRule(Rule):
    id: ClassVar[str] = "SEC003"
    description: ClassVar[str] = (
        "Dangerous deserialization function used — can execute arbitrary code"
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "vulnerability", "deserialization")

    @classmethod
    def should_check(cls, source: str) -> bool:
        tokens = ("pickle", "marshal", "shelve", "yaml", "jsonpickle")
        return any(t in source for t in tokens)

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        call_nodes = node_index.get(ast.Call, []) if node_index else []
        if not call_nodes:
            call_nodes = (n for n in ast.walk(tree) if isinstance(n, ast.Call))

        for node in call_nodes:
            module_name, func_name = _get_call_info(node)
            if module_name is None or func_name is None:
                continue

            if module_name in _YAML_MODULE_NAMES and func_name == "load":
                if _is_yaml_load_unsafe(node):
                    has_loader_kw = any(kw.arg == "Loader" for kw in node.keywords)
                    explanation = (
                        "yaml.load() with an unsafe Loader can execute arbitrary code. "
                        "Use yaml.safe_load() or pass Loader=yaml.SafeLoader."
                        if has_loader_kw
                        else "yaml.load() without an explicit Loader uses the default "
                        "(unsafe) Loader, which can execute arbitrary code. "
                        "Use yaml.safe_load() or pass Loader=yaml.SafeLoader."
                    )
                    violations.append(
                        self._make_violation(
                            node,
                            "Use yaml.safe_load() or yaml.load(..., Loader=yaml.SafeLoader)",
                            explanation,
                            filename,
                        )
                    )
                continue

            if module_name in _YAML_MODULE_NAMES and func_name == "safe_load":
                continue

            if module_name in _DANGEROUS_CALLS:
                funcs = _DANGEROUS_CALLS[module_name]
                if func_name in funcs:
                    _, title, explanation = funcs[func_name]
                    violations.append(
                        self._make_violation(node, title, explanation, filename)
                    )

        return violations

    def _make_violation(
        self,
        node: ast.Call,
        fix_title: str,
        fix_explanation: str,
        filename: str,
    ) -> Violation:
        module_name, func_name = _get_call_info(node)
        return Violation(
            rule_id=self.id,
            message=(
                f"Dangerous deserialization: `{module_name}.{func_name}()` "
                f"can execute arbitrary code with untrusted input"
            ),
            location=Location(
                row=node.lineno,
                column=node.col_offset,
            ),
            end_location=Location(
                row=node.end_lineno or node.lineno,
                column=node.end_col_offset or node.col_offset,
            ),
            severity=self.severity,
            fix=FixSuggestion(
                title=fix_title,
                replacement=None,
                explanation=fix_explanation,
            ),
            filename=filename,
        )
