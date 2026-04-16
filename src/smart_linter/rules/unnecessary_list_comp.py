"""PERF002: Detect unnecessary list comprehensions passed to iterable-consuming functions."""

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

ITERABLE_CONSUMERS = frozenset(
    {
        "any",
        "all",
        "sum",
        "min",
        "max",
        "tuple",
        "set",
        "frozenset",
        "sorted",
        "enumerate",
        "list",
    }
)


def _unparse_listcomp_as_gen(node: ast.ListComp) -> str:
    """Convert a ListComp AST node to a generator-expression string."""
    elt = ast.unparse(node.elt)
    generators = []
    for gen in node.generators:
        target = ast.unparse(gen.target)
        iter_val = ast.unparse(gen.iter)
        ifs = ""
        if gen.ifs:
            ifs = " if " + " if ".join(ast.unparse(i) for i in gen.ifs)
        generators.append(f"for {target} in {iter_val}{ifs}")
    return f"{elt} {' '.join(generators)}"


class UnnecessaryListCompRule(Rule):
    id: ClassVar[str] = "PERF002"
    description: ClassVar[str] = (
        "Unnecessary list comprehension — use generator expression instead"
    )
    severity: ClassVar[Severity] = Severity.INFO
    tags: ClassVar[tuple[str, ...]] = ("performance",)

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        call_nodes = node_index.get(ast.Call, []) if node_index else []
        if not call_nodes:
            call_nodes = (n for n in ast.walk(tree) if isinstance(n, ast.Call))

        for node in call_nodes:
            if not isinstance(node.func, ast.Name):
                continue

            func_name = node.func.id
            if func_name not in ITERABLE_CONSUMERS:
                continue

            if not node.args:
                continue

            first_arg = node.args[0]
            if not isinstance(first_arg, ast.ListComp):
                continue

            gen_expr = _unparse_listcomp_as_gen(first_arg)
            replacement = f"{func_name}({gen_expr})"

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Unnecessary list comprehension in `{func_name}()` — "
                        f"use a generator expression instead"
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
                        title="Replace list comprehension with generator expression",
                        replacement=replacement,
                        explanation=(
                            f"`{func_name}([...])` creates an intermediate list in memory. "
                            f"`{func_name}(...)` uses a generator, avoiding the allocation."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
