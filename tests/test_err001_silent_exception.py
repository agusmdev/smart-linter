"""Tests for ERR001 rule: silent exception swallowing."""

import ast

from smart_linter.rules.silent_exception import SilentExceptionRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = SilentExceptionRule()
    return rule.check(tree, filename=filename)


def test_bare_except_pass():
    code = """
try:
    risky()
except:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "ERR001"
    assert "bare except" in violations[0].message


def test_except_exception_pass():
    code = """
try:
    risky()
except Exception:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "ERR001"
    assert violations[0].fix is not None
    assert "logger.exception" in violations[0].fix.replacement


def test_except_specific_error_pass():
    code = """
try:
    risky()
except ValueError:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "ValueError" in violations[0].message


def test_no_violation_with_logging_error():
    code = """
import logging
try:
    risky()
except ValueError:
    logging.error("Something failed")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_raise():
    code = """
try:
    risky()
except ValueError:
    raise
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_continue():
    code = """
for item in items:
    try:
        process(item)
    except ValueError:
        continue
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_ellipsis_body_detected():
    code = """
try:
    risky()
except ValueError as e:
    ...
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "ValueError" in violations[0].message


def test_no_violation_with_logger_warning():
    code = """
try:
    risky()
except ValueError as e:
    logger.warning("Failed: %s", e)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assignment_only_detected():
    code = """
try:
    risky()
except ValueError as e:
    x = 1
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_underscore_assignment_detected():
    code = """
try:
    risky()
except ValueError as e:
    _ = e
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_multiple_handlers_only_silent_flagged():
    code = """
import logging
try:
    risky()
except ValueError:
    logging.error("val error")
except TypeError:
    pass
except KeyError:
    raise
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "TypeError" in violations[0].message


def test_nested_try_inner_silent_detected():
    code = """
try:
    try:
        inner()
    except ValueError:
        pass
except Exception:
    logging.error("outer")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "ValueError" in violations[0].message


def test_no_violation_with_sys_exit():
    code = """
import sys
try:
    risky()
except ValueError:
    sys.exit(1)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_print():
    code = """
try:
    risky()
except ValueError:
    print("error occurred")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_bare_except_fix_mentions_pep760():
    code = """
try:
    risky()
except:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert "PEP 760" in fix.explanation
    assert "SpecificError" in fix.replacement


def test_specific_error_fix_includes_type():
    code = """
try:
    risky()
except IOError:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert "IOError" in fix.replacement
    assert "logger.warning" in fix.replacement


def test_no_violation_with_break():
    code = """
for item in items:
    try:
        process(item)
    except ValueError:
        break
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_warnings_warn():
    code = """
import warnings
try:
    risky()
except ValueError:
    warnings.warn("deprecated behavior")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_empty_try():
    code = """
x = 1 + 2
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_location_correct():
    code = """
try:
    risky()
except ValueError:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].location.row == 4
    assert violations[0].filename == "test.py"


def test_multiple_silent_handlers_all_detected():
    code = """
try:
    risky()
except ValueError:
    pass
except TypeError:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_underscore_and_pass_detected():
    code = """
try:
    risky()
except ValueError as e:
    _ = e
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_no_violation_with_traceback_print_exc():
    code = """
import traceback
try:
    risky()
except Exception:
    traceback.print_exc()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_return_none():
    code = """
try:
    risky()
except Exception:
    return None
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_return_value():
    code = """
try:
    risky()
except ValueError:
    return -1
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_uppercase_assignment():
    code = """
try:
    from importlib.metadata import version
    VERSION = version("my-package")
except Exception:
    VERSION = "unknown"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_http_exception_pass():
    code = """
try:
    risky()
except HTTPException:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_http_exception_in_tuple():
    code = """
try:
    risky()
except (HTTPException, ValueError):
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_except_exception_pass_still_detected():
    code = """
try:
    risky()
except Exception:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "ERR001"


def test_get_qualified_name_returns_none_for_non_name_attr():
    from smart_linter.rules.silent_exception import _get_qualified_name

    assert _get_qualified_name(ast.Constant(value=1)) is None


def test_meaningful_call_logging_submodule():
    from smart_linter.rules.silent_exception import _is_meaningful_call

    code = "logging.handlers.some_func()"
    tree = ast.parse(code)
    call_func = tree.body[0].value.func
    assert _is_meaningful_call(call_func) is True


def test_meaningful_call_non_matching():
    from smart_linter.rules.silent_exception import _is_meaningful_call

    code = "something.other()"
    tree = ast.parse(code)
    call_func = tree.body[0].value.func
    assert _is_meaningful_call(call_func) is False


def test_meaningful_call_none_qualified_name():
    from smart_linter.rules.silent_exception import _is_meaningful_call

    assert _is_meaningful_call(ast.Subscript(value=ast.Name(id="x"))) is False


def test_augassign_with_call_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    result += compute()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_annassign_with_call_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    x: int = compute()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_non_meaningful_call_detected():
    code = """
try:
    risky()
except ValueError:
    something()
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_assign_with_call_value_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    x = compute_error()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_with_uppercase_target_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    STATUS = compute()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_assign_with_tuple_call_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    a, b = compute()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_non_pass_non_meaningful_stmt_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    if True:
        pass
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_control_flow_non_name_type():
    code = """
try:
    risky()
except (ValueError,):
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_describe_exc_type_non_name():
    code = """
try:
    risky()
except (ValueError, TypeError):
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_except_named_with_fix():
    code = """
try:
    risky()
except Exception as e:
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert " as e" in violations[0].fix.replacement


def test_empty_handler_body():
    from smart_linter.rules.silent_exception import SilentExceptionRule

    handler = ast.ExceptHandler(type=ast.Name(id="ValueError"), name=None, body=[])
    rule = SilentExceptionRule()
    assert rule._is_silent_handler(handler) is True


def test_non_meaningful_call_continues():
    code = """
try:
    risky()
except ValueError:
    something.random()
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_expr_non_constant_continues():
    code = """
try:
    risky()
except ValueError:
    x
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_augassign_non_call_continues():
    code = """
try:
    risky()
except ValueError:
    x += 1
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_annassign_non_call_continues():
    code = """
try:
    risky()
except ValueError:
    x: int = 42
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_unrecognized_stmt_is_meaningful():
    code = """
try:
    risky()
except ValueError:
    for x in y:
        pass
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_tuple_exception_not_control_flow():
    code = """
try:
    risky()
except (ValueError, TypeError):
    pass
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_meaningful_call_prefix_dot_match():
    from smart_linter.rules.silent_exception import _is_meaningful_call

    code = "logging.info.extra()"
    tree = ast.parse(code)
    call_func = tree.body[0].value.func
    assert _is_meaningful_call(call_func) is True

    code2 = """
try:
    risky()
except ValueError:
    logging.info("error occurred")
"""
    violations = _check_code(code2)
    assert len(violations) == 0


def test_tuple_unpack_assign_in_handler():
    code = """
try:
    risky()
except ValueError:
    x, y = compute(), compute()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_non_control_flow_tuple_exception():
    from smart_linter.rules.silent_exception import _is_control_flow_exception

    code = """
try:
    pass
except (RuntimeError, KeyError):
    pass
"""
    tree = ast.parse(code)
    handler = tree.body[0].handlers[0]
    assert _is_control_flow_exception(handler) is False


def test_attribute_exception_not_control_flow():
    from smart_linter.rules.silent_exception import _is_control_flow_exception

    code = """
try:
    pass
except custom_module.Error:
    pass
"""
    tree = ast.parse(code)
    handler = tree.body[0].handlers[0]
    assert _is_control_flow_exception(handler) is False
