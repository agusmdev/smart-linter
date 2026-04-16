"""Shared AST utility functions for smart-linter rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


def build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Build a mapping from each node to its parent."""
    parent_map: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    return parent_map


def get_qualified_name(node: ast.expr) -> str | None:
    """Get the fully qualified name of an AST node (e.g. 'requests.get')."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = get_qualified_name(node.value)
        if value:
            return f"{value}.{node.attr}"
    return None


def get_import_aliases(tree: ast.AST) -> dict[str, str]:
    """Parse import statements and return alias -> module mapping.

    Handles: ``import X``, ``import X as Y``, ``from X import Y``,
    ``from X import Y as Z``, ``from X import (Y, Z as W)``.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # import X       -> X -> X
                # import X as Y  -> Y -> X
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                # from X import Y      -> Y -> X.Y
                # from X import Y as Z -> Z -> X.Y
                local = alias.asname or alias.name
                aliases[local] = f"{module}.{alias.name}"
    return aliases


@dataclass
class TreeAnalysis:
    """Result of a single-pass tree analysis."""

    parent_map: dict[ast.AST, ast.AST] = field(default_factory=dict)
    function_index: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = field(
        default_factory=dict
    )
    imports: dict[str, str] = field(default_factory=dict)
    class_definitions: dict[str, ast.ClassDef] = field(default_factory=dict)
    string_constants: dict[str, list[ast.Constant]] = field(default_factory=dict)


def analyze_tree(tree: ast.AST) -> TreeAnalysis:
    """Single-pass tree analysis computing parent map, function index, imports,
    class definitions, and string constants."""
    result = TreeAnalysis()

    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            result.parent_map[child] = node

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.function_index[node.name] = node

        if isinstance(node, ast.Import):
            for alias in node.names:
                result.imports[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                result.imports[local] = f"{module}.{alias.name}"

        if isinstance(node, ast.ClassDef):
            result.class_definitions[node.name] = node

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            result.string_constants.setdefault(node.value, []).append(node)

    return result


def is_in_context(
    node: ast.AST,
    parent_map: dict[ast.AST, ast.AST],
    context_type: type,
) -> bool:
    """Check if *node* is inside a parent of *context_type*.

    Walks up the parent chain and returns ``True`` as soon as a parent
    matching *context_type* is found.
    """
    parent = parent_map.get(node)
    while parent is not None:
        if isinstance(parent, context_type):
            return True
        parent = parent_map.get(parent)
    return False
