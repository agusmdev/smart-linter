"""Tests for PERF002 rule: unnecessary list comprehension in iterable consumers."""

import ast

from smart_linter.rules.unnecessary_list_comp import UnnecessaryListCompRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = UnnecessaryListCompRule()
    return rule.check(tree, filename=filename)


def test_detects_any_with_list_comp():
    code = "result = any([x > 0 for x in data])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "PERF002"
    assert "any" in violations[0].message


def test_detects_sum_with_list_comp():
    code = "total = sum([x.price for x in products])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "sum" in violations[0].message


def test_detects_all_with_list_comp():
    code = "found = all([is_valid(x) for x in items])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "all" in violations[0].message


def test_detects_max_with_list_comp():
    code = "result = max([x.score for x in players])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "max" in violations[0].message


def test_detects_min_with_list_comp():
    code = "result = min([x.score for x in players])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "min" in violations[0].message


def test_detects_tuple_with_list_comp():
    code = "result = tuple([x for x in data])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "tuple" in violations[0].message


def test_detects_set_with_list_comp():
    code = "result = set([x.id for x in items])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "set" in violations[0].message


def test_detects_frozenset_with_list_comp():
    code = "result = frozenset([x.id for x in items])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "frozenset" in violations[0].message


def test_detects_sorted_with_list_comp():
    code = "result = sorted([x.name for x in items])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "sorted" in violations[0].message


def test_detects_enumerate_with_list_comp():
    code = "result = enumerate([x for x in items])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "enumerate" in violations[0].message


def test_detects_list_with_list_comp():
    code = "result = list([x for x in items])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert "list" in violations[0].message


def test_no_violation_for_generator_expression():
    code = "result = any(x > 0 for x in data)"
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_unknown_function():
    code = "result = my_func([x for x in data])"
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_method_call():
    code = "result = obj.any([x for x in data])"
    violations = _check_code(code)
    assert len(violations) == 0


def test_fix_suggestion_replaces_brackets():
    code = "result = any([x > 0 for x in data])"
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert fix.replacement == "any(x > 0 for x in data)"
    assert "generator" in fix.explanation.lower()


def test_fix_suggestion_with_filter():
    code = "result = sum([x.price for x in products if x.in_stock])"
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert fix.replacement == "sum(x.price for x in products if x.in_stock)"


def test_severity_is_info():
    code = "result = any([x for x in data])"
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].severity.value == "info"


def test_tags_include_performance():
    assert "performance" in UnnecessaryListCompRule.tags


def test_multiple_violations():
    code = """
result1 = any([x for x in data])
result2 = sum([y for y in items])
"""
    violations = _check_code(code)
    assert len(violations) == 2
    assert "any" in violations[0].message
    assert "sum" in violations[1].message


def test_consumer_with_no_args_not_flagged():
    code = "x = list()"
    violations = _check_code(code)
    assert len(violations) == 0
