"""Tests for smart_linter.ast_utils."""

from __future__ import annotations

import ast

import pytest

from smart_linter.ast_utils import (
    TreeAnalysis,
    analyze_tree,
    build_parent_map,
    get_import_aliases,
    get_qualified_name,
    is_in_context,
)


# ---------------------------------------------------------------------------
# build_parent_map
# ---------------------------------------------------------------------------


class TestBuildParentMap:
    def test_simple_module(self):
        tree = ast.parse("x = 1")
        pmap = build_parent_map(tree)
        assert len(pmap) > 0

    def test_assign_target_parent_is_module(self):
        tree = ast.parse("x = 1")
        pmap = build_parent_map(tree)
        assign = tree.body[0]
        target = assign.targets[0]
        assert pmap[target] is assign

    def test_function_body_parent_is_function(self):
        tree = ast.parse("def foo(): pass")
        pmap = build_parent_map(tree)
        func = tree.body[0]
        body_stmt = func.body[0]
        assert pmap[body_stmt] is func

    def test_nested_structure(self):
        source = """
class MyClass:
    def method(self):
        x = 1
"""
        tree = ast.parse(source)
        pmap = build_parent_map(tree)
        class_def = tree.body[0]
        func_def = class_def.body[0]
        assign = func_def.body[0]
        assert pmap[func_def] is class_def
        assert pmap[assign] is func_def

    def test_empty_module(self):
        tree = ast.parse("")
        pmap = build_parent_map(tree)
        assert isinstance(pmap, dict)

    def test_all_nodes_have_parents_except_root(self):
        tree = ast.parse("x = 1\ny = 2")
        pmap = build_parent_map(tree)
        for node in ast.walk(tree):
            if node is tree:
                assert node not in pmap
            else:
                has_parent_or_grandchild = node in pmap or any(
                    node is c for children in (ast.iter_child_nodes(p) for p in pmap) for c in children
                )


# ---------------------------------------------------------------------------
# get_qualified_name
# ---------------------------------------------------------------------------


class TestGetQualifiedName:
    def test_simple_name(self):
        node = ast.Name(id="requests", ctx=ast.Load())
        assert get_qualified_name(node) == "requests"

    def test_attribute_access(self):
        expr = ast.parse("a.b.c", mode="eval")
        result = get_qualified_name(expr.body)
        assert result == "a.b.c"

    def test_single_attribute(self):
        expr = ast.parse("obj.attr", mode="eval")
        result = get_qualified_name(expr.body)
        assert result == "obj.attr"

    def test_returns_none_for_non_name_non_attr(self):
        node = ast.Constant(value=42)
        assert get_qualified_name(node) is None

    def test_method_call_chain(self):
        expr = ast.parse("requests.get.url", mode="eval")
        result = get_qualified_name(expr.body)
        assert result == "requests.get.url"

    def test_nested_attribute_with_call_returns_none(self):
        expr = ast.parse("a.b()", mode="eval")
        call_node = expr.body
        attr_node = call_node.func
        result = get_qualified_name(attr_node)
        assert result == "a.b"


# ---------------------------------------------------------------------------
# get_import_aliases
# ---------------------------------------------------------------------------


class TestGetImportAliases:
    def test_import_x(self):
        tree = ast.parse("import os")
        aliases = get_import_aliases(tree)
        assert aliases == {"os": "os"}

    def test_import_x_as_y(self):
        tree = ast.parse("import numpy as np")
        aliases = get_import_aliases(tree)
        assert aliases == {"np": "numpy"}

    def test_from_x_import_y(self):
        tree = ast.parse("from os.path import join")
        aliases = get_import_aliases(tree)
        assert aliases == {"join": "os.path.join"}

    def test_from_x_import_y_as_z(self):
        tree = ast.parse("from os.path import join as j")
        aliases = get_import_aliases(tree)
        assert aliases == {"j": "os.path.join"}

    def test_multiple_from_imports(self):
        tree = ast.parse("from collections import OrderedDict, defaultdict")
        aliases = get_import_aliases(tree)
        assert aliases == {
            "OrderedDict": "collections.OrderedDict",
            "defaultdict": "collections.defaultdict",
        }

    def test_mixed_aliases(self):
        tree = ast.parse("import os\nimport numpy as np\nfrom sys import path")
        aliases = get_import_aliases(tree)
        assert aliases["os"] == "os"
        assert aliases["np"] == "numpy"
        assert aliases["path"] == "sys.path"

    def test_empty_module(self):
        tree = ast.parse("")
        aliases = get_import_aliases(tree)
        assert aliases == {}

    def test_multiple_imports_same_line(self):
        tree = ast.parse("import os, sys")
        aliases = get_import_aliases(tree)
        assert aliases == {"os": "os", "sys": "sys"}


# ---------------------------------------------------------------------------
# analyze_tree
# ---------------------------------------------------------------------------


class TestAnalyzeTree:
    def test_returns_tree_analysis(self):
        tree = ast.parse("x = 1")
        result = analyze_tree(tree)
        assert isinstance(result, TreeAnalysis)

    def test_parent_map_populated(self):
        tree = ast.parse("x = 1")
        result = analyze_tree(tree)
        assert len(result.parent_map) > 0

    def test_function_index_sync(self):
        source = """
def foo():
    pass

def bar():
    return 1
"""
        tree = ast.parse(source)
        result = analyze_tree(tree)
        assert "foo" in result.function_index
        assert "bar" in result.function_index
        assert isinstance(result.function_index["foo"], ast.FunctionDef)

    def test_function_index_async(self):
        tree = ast.parse("async def afoo(): pass")
        result = analyze_tree(tree)
        assert "afoo" in result.function_index
        assert isinstance(result.function_index["afoo"], ast.AsyncFunctionDef)

    def test_imports_populated(self):
        tree = ast.parse("import os\nfrom sys import path")
        result = analyze_tree(tree)
        assert result.imports["os"] == "os"
        assert result.imports["path"] == "sys.path"

    def test_class_definitions(self):
        tree = ast.parse("class Foo: pass\nclass Bar: pass")
        result = analyze_tree(tree)
        assert "Foo" in result.class_definitions
        assert "Bar" in result.class_definitions
        assert isinstance(result.class_definitions["Foo"], ast.ClassDef)

    def test_string_constants(self):
        tree = ast.parse("'hello'\n'world'\n'hello'")
        result = analyze_tree(tree)
        assert "hello" in result.string_constants
        assert len(result.string_constants["hello"]) == 2
        assert "world" in result.string_constants

    def test_empty_module(self):
        tree = ast.parse("")
        result = analyze_tree(tree)
        assert len(result.parent_map) == 0
        assert len(result.function_index) == 0
        assert len(result.imports) == 0
        assert len(result.class_definitions) == 0
        assert len(result.string_constants) == 0

    def test_integer_constants_not_in_string_constants(self):
        tree = ast.parse("42")
        result = analyze_tree(tree)
        assert len(result.string_constants) == 0

    def test_complex_tree(self):
        source = """
import os
from pathlib import Path

class Config:
    def load(self):
        data = "config.yaml"
        return data

async def process():
    pass
"""
        tree = ast.parse(source)
        result = analyze_tree(tree)
        assert "os" in result.imports
        assert "Path" in result.imports
        assert "Config" in result.class_definitions
        assert "load" in result.function_index
        assert "process" in result.function_index
        assert "config.yaml" in result.string_constants


# ---------------------------------------------------------------------------
# is_in_context
# ---------------------------------------------------------------------------


class TestIsInContext:
    def test_inside_function(self):
        tree = ast.parse("def foo(): x = 1")
        pmap = build_parent_map(tree)
        func = tree.body[0]
        assign = func.body[0]
        assert is_in_context(assign, pmap, ast.FunctionDef) is True

    def test_not_inside_function(self):
        tree = ast.parse("x = 1")
        pmap = build_parent_map(tree)
        assign = tree.body[0]
        assert is_in_context(assign, pmap, ast.FunctionDef) is False

    def test_inside_async_function(self):
        tree = ast.parse("async def afoo(): x = 1")
        pmap = build_parent_map(tree)
        func = tree.body[0]
        assign = func.body[0]
        assert is_in_context(assign, pmap, ast.AsyncFunctionDef) is True

    def test_inside_class(self):
        tree = ast.parse("class Foo:\n    x = 1")
        pmap = build_parent_map(tree)
        class_def = tree.body[0]
        assign = class_def.body[0]
        assert is_in_context(assign, pmap, ast.ClassDef) is True

    def test_nested_function_inside_class(self):
        source = """
class MyClass:
    def method(self):
        x = 1
"""
        tree = ast.parse(source)
        pmap = build_parent_map(tree)
        class_def = tree.body[0]
        func = class_def.body[0]
        assign = func.body[0]
        assert is_in_context(assign, pmap, ast.ClassDef) is True
        assert is_in_context(assign, pmap, ast.FunctionDef) is True

    def test_node_not_in_pmap(self):
        tree = ast.parse("x = 1")
        pmap = build_parent_map(tree)
        orphan = ast.Name(id="orphan", ctx=ast.Load())
        assert is_in_context(orphan, pmap, ast.FunctionDef) is False

    def test_root_node_not_in_any_context(self):
        tree = ast.parse("x = 1")
        pmap = build_parent_map(tree)
        assert is_in_context(tree, pmap, ast.FunctionDef) is False
