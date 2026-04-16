"""Tests for PRINT002 rule: print() in async functions."""

import ast

from smart_linter.rules.print_in_async import PrintInAsyncRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = PrintInAsyncRule()
    return rule.check(tree, filename=filename)


def test_print_in_async_detected():
    code = """
async def hello():
    print("hello")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "PRINT002"


def test_no_print_in_sync():
    code = """
def hello():
    print("hello")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_print_no_async():
    code = """
print("top level")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_location():
    code = """
async def hello():
    print("hello")
"""
    violations = _check_code(code)
    assert violations[0].location.row == 3


def test_should_check():
    assert PrintInAsyncRule.should_check('async def f():\n    print("x")') is True
    assert PrintInAsyncRule.should_check('def f():\n    print("x")') is False
    assert PrintInAsyncRule.should_check('async def f():\n    pass') is False
