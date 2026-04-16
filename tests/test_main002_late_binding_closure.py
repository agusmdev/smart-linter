"""Tests for MAIN002: late binding closure in loops."""

import ast

from smart_linter.rules.late_binding_closure import LateBindingClosureRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = LateBindingClosureRule()
    return rule.check(tree, filename=filename)


def test_lambda_captures_loop_var():
    code = """
funcs = []
for i in range(10):
    funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_while_else_with_closure():
    code = """
funcs = []
for i in range(10):
    while True:
        break
    else:
        funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_lambda_captured_by_value_not_flagged():
    code = """
funcs = []
for i in range(10):
    funcs.append(lambda i=i: i)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_def_captures_loop_var():
    code = """
handlers = []
for i in range(10):
    def handler():
        return i
    handlers.append(handler)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "MAIN002"
    assert "handler" in violations[0].message
    assert "i" in violations[0].message


def test_def_captured_by_value_not_flagged():
    code = """
handlers = []
for i in range(10):
    def handler(i=i):
        return i
    handlers.append(handler)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_different_var_not_flagged():
    code = """
x = 5
funcs = []
for i in range(10):
    funcs.append(lambda: x)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_lambda_outside_loop_not_flagged():
    code = """
i = 42
f = lambda: i
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_nested_loop_outer_var_detected():
    code = """
funcs = []
for i in range(5):
    for j in range(5):
        funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_while_loop_captures_outer_for_var():
    code = """
funcs = []
for i in range(10):
    while True:
        funcs.append(lambda: i)
        break
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_multiple_lambdas_each_detected():
    code = """
funcs = []
for i in range(10):
    funcs.append(lambda: i)
    funcs.append(lambda: i + 1)
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_tuple_unpacking_detected():
    code = """
funcs = []
for i, j in [(1, 2), (3, 4)]:
    funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_tuple_unpacking_second_var():
    code = """
funcs = []
for i, j in [(1, 2), (3, 4)]:
    funcs.append(lambda: j)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "j" in violations[0].message


def test_async_def_captures_loop_var():
    code = """
handlers = []
for item in items:
    async def handler():
        return item
    handlers.append(handler)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "handler" in violations[0].message
    assert "item" in violations[0].message


def test_violation_has_fix_suggestion():
    code = """
funcs = []
for i in range(10):
    funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert fix.replacement == "i=i"
    assert fix.explanation is not None
    assert "i=i" in fix.explanation


def test_lambda_only_flags_used_vars():
    code = """
results = []
for i in range(10):
    results.append(lambda x: x)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_inner_loop_shadows_outer_var():
    code = """
funcs = []
for i in range(5):
    for i in range(3):
        funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_loop_var_used_in_closure_expression():
    code = """
results = []
for val in values:
    results.append(lambda: val * 2)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "val" in violations[0].message


def test_def_with_param_shadows_loop_var():
    code = """
handlers = []
for i in range(10):
    def handler(i):
        return i
    handlers.append(handler)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_starred_target_returns_empty():
    code = """
funcs = []
for *args in [[1, 2, 3]]:
    funcs.append(lambda: args)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_lambda_with_posonly_arg_captures_loop_var():
    code = """
funcs = []
for i in range(10):
    funcs.append(lambda a, /, x=i: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_lambda_with_kwonly_arg_captures_loop_var():
    code = """
funcs = []
for i in range(10):
    funcs.append(lambda *, x: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_def_with_vararg_captures_loop_var():
    code = """
handlers = []
for i in range(10):
    def handler(*args):
        return i
    handlers.append(handler)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_def_with_kwarg_captures_loop_var():
    code = """
handlers = []
for i in range(10):
    def handler(**kwargs):
        return i
    handlers.append(handler)
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_should_check_returns_true_for_while():
    assert LateBindingClosureRule.should_check("while True:\n    pass") is True


def test_while_loop_direct_closures():
    code = """
for i in range(10):
    while True:
        funcs.append(lambda: i)
        break
"""
    violations = _check_code(code)
    assert len(violations) >= 1
    assert any("i" in v.message for v in violations)


def test_for_else_with_closure():
    code = """
funcs = []
for i in range(10):
    pass
else:
    funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "i" in violations[0].message


def test_for_else_recursive_check():
    code = """
funcs = []
for i in range(10):
    if True:
        funcs.append(lambda: i)
else:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_while_loop_body_and_orelse():
    code = """
for i in range(10):
    while condition:
        funcs.append(lambda: i)
        break
    else:
        funcs.append(lambda: i)
"""
    violations = _check_code(code)
    assert len(violations) >= 1
    assert any("i" in v.message for v in violations)


def test_while_no_loop_vars_no_violation():
    code = """
funcs = []
x = 5
while True:
    funcs.append(lambda: x)
    break
"""
    violations = _check_code(code)
    assert len(violations) == 0
