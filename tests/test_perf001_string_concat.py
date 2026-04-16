"""Tests for PERF001: string concatenation using += inside loops."""

import ast

from smart_linter.rules.string_concat_loop import StringConcatLoopRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = StringConcatLoopRule()
    return rule.check(tree, filename=filename)


def test_detects_string_concat_in_for_loop():
    code = """
result = ""
for item in items:
    result += f"Item: {item}\\n"
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "PERF001"
    assert "result" in violations[0].message


def test_detects_string_concat_in_while_loop():
    code = """
text = ""
while condition:
    text += more_text
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "PERF001"


def test_no_detection_outside_loop():
    code = """
result = ""
result += "hello"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_in_nested_function_inside_loop():
    code = """
result = ""
for item in items:
    def helper():
        result += "x"
    helper()
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_detects_assign_with_add_in_loop():
    code = """
result = ""
for item in items:
    result = result + str(item)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "PERF001" == violations[0].rule_id


def test_multiple_concats_in_same_loop():
    code = """
result = ""
for item in items:
    result += "a"
    result += "b"
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_no_detection_in_list_comprehension():
    code = """
result = ""
parts = [result + x for x in items]
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_detection_for_int_counter():
    code = """
count = 0
for item in items:
    count += 1
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_has_fix_suggestion():
    code = """
result = ""
for item in items:
    result += str(item)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert violations[0].fix.replacement is not None
    assert "join" in violations[0].fix.replacement
    assert "append" in violations[0].fix.replacement


def test_detects_in_async_for_loop():
    code = """
result = ""
async for chunk in stream:
    result += chunk
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_no_detection_when_not_self_referencing():
    code = """
result = ""
other = ""
for item in items:
    result = other + str(item)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_detection_without_string_init():
    code = """
result = something()
for item in items:
    result += str(item)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_severity_is_info():
    code = """
result = ""
for item in items:
    result += "x"
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].severity.value == "info"


def test_multi_target_init_not_tracked():
    code = """
a = b = ""
for item in items:
    a += "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_non_name_init_target_not_tracked():
    code = """
items[0] = ""
for item in items:
    items[0] += "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_inside_comprehension_not_flagged():
    code = """
result = ""
parts = [result for x in items]
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_augassign_non_name_target():
    code = """
result = ""
items[0] = ""
for item in items:
    items[0] += "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_non_add_op():
    code = """
result = ""
for item in items:
    result = result - "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_multi_target():
    code = """
result = other = ""
for item in items:
    result = result + "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_non_name_target():
    code = """
result = ""
for item in items:
    items[0] = items[0] + "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_not_self_referencing():
    code = """
result = ""
other = ""
for item in items:
    result = other + "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_outside_loop():
    code = """
result = ""
result = result + "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_inside_comprehension():
    code = """
result = ""
x = [result + "a" for item in items]
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_add_no_string_init():
    code = """
result = something()
for item in items:
    result = result + "x"
"""
    violations = _check_code(code)
    assert len(violations) == 0
