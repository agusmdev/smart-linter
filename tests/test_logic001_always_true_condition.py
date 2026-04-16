"""Tests for LOGIC001: always-true / always-false conditions."""

import ast

from smart_linter.rules.always_true_condition import AlwaysTrueConditionRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = AlwaysTrueConditionRule()
    return rule.check(tree, filename=filename)


def test_if_x_and_x():
    violations = _check_code("if x and x:\n    pass\n")
    assert len(violations) == 1
    assert violations[0].rule_id == "LOGIC001"
    assert "`x and x`" in violations[0].message
    assert violations[0].fix is not None
    assert "duplicate" in violations[0].fix.title.lower()


def test_if_x_or_not_x():
    violations = _check_code("if x or not x:\n    pass\n")
    assert len(violations) == 1
    assert "`x or not x`" in violations[0].message
    assert "always true" in violations[0].message


def test_if_x_and_not_x():
    violations = _check_code("if x and not x:\n    pass\n")
    assert len(violations) == 1
    assert "`x and not x`" in violations[0].message
    assert "always false" in violations[0].message


def test_if_x_eq_x():
    violations = _check_code("if x == x:\n    pass\n")
    assert len(violations) == 1
    assert "`x == x`" in violations[0].message
    assert "always true" in violations[0].message
    assert violations[0].fix is not None
    assert "typo" in violations[0].fix.title.lower()


def test_if_x_ne_x():
    violations = _check_code("if x != x:\n    pass\n")
    assert len(violations) == 1
    assert "`x != x`" in violations[0].message
    assert "always false" in violations[0].message
    assert "nan" in violations[0].fix.explanation.lower()


def test_if_x_and_y_no_violation():
    violations = _check_code("if x and y:\n    pass\n")
    assert len(violations) == 0


def test_if_x_eq_y_no_violation():
    violations = _check_code("if x == y:\n    pass\n")
    assert len(violations) == 0


def test_while_x_and_x():
    violations = _check_code("while x and x:\n    pass\n")
    assert len(violations) == 1
    assert "`x and x`" in violations[0].message


def test_ternary_x_and_x():
    violations = _check_code("result = x if x and x else y\n")
    assert len(violations) == 1
    assert "`x and x`" in violations[0].message


def test_assert_x_and_x():
    violations = _check_code("assert x and x\n")
    assert len(violations) == 1
    assert "`x and x`" in violations[0].message


def test_isinstance_x_type_x():
    violations = _check_code("if isinstance(x, type(x)):\n    pass\n")
    assert len(violations) == 1
    assert "isinstance(x, type(x))" in violations[0].message
    assert "always true" in violations[0].message


def test_if_x_is_x():
    violations = _check_code("if x is x:\n    pass\n")
    assert len(violations) == 1
    assert "`x is x`" in violations[0].message
    assert "always true" in violations[0].message


def test_not_x_and_x():
    violations = _check_code("if not x and x:\n    pass\n")
    assert len(violations) == 1
    assert "`not x and x`" in violations[0].message
    assert "always false" in violations[0].message


def test_not_x_or_x():
    violations = _check_code("if not x or x:\n    pass\n")
    assert len(violations) == 1
    assert "`not x or x`" in violations[0].message
    assert "always true" in violations[0].message


def test_x_or_x():
    violations = _check_code("if x or x:\n    pass\n")
    assert len(violations) == 1
    assert "`x or x`" in violations[0].message


def test_nested_boolop():
    violations = _check_code("if (x and x) or y:\n    pass\n")
    assert len(violations) == 1
    assert "`x and x`" in violations[0].message


def test_fix_suggestion_present():
    violations = _check_code("if x and x:\n    pass\n")
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert fix.title
    assert fix.replacement is not None
    assert fix.explanation is not None


def test_compare_self_is():
    violations = _check_code("if x is x:\n    pass\n")
    assert len(violations) == 1
    assert "`x is x`" in violations[0].message


def test_isinstance_type_no_args():
    violations = _check_code("if isinstance(x):\n    pass\n")
    assert len(violations) == 0


def test_isinstance_type_second_not_call():
    violations = _check_code("if isinstance(x, int):\n    pass\n")
    assert len(violations) == 0


def test_isinstance_type_second_not_type_call():
    violations = _check_code("if isinstance(x, list()):\n    pass\n")
    assert len(violations) == 0


def test_isinstance_type_no_single_arg():
    violations = _check_code("if isinstance(x, type()):\n    pass\n")
    assert len(violations) == 0


def test_isinstance_type_different_vars():
    violations = _check_code("if isinstance(x, type(y)):\n    pass\n")
    assert len(violations) == 0


def test_should_check_returns_true():
    assert AlwaysTrueConditionRule.should_check("if x:\n    pass") is True


def test_should_check_returns_false():
    assert AlwaysTrueConditionRule.should_check("x = 1") is False


def test_not_condition_check():
    violations = _check_code("if not (x and x):\n    pass\n")
    assert len(violations) == 1
    assert "`x and x`" in violations[0].message


def test_compare_lt_self_no_violation():
    violations = _check_code("if x < x:\n    pass\n")
    assert len(violations) == 0


def test_compare_gt_self_no_violation():
    violations = _check_code("if x > x:\n    pass\n")
    assert len(violations) == 0


def test_non_isinstance_call_not_flagged():
    violations = _check_code("if foo():\n    pass\n")
    assert len(violations) == 0
