"""Tests for SEC003 rule: dangerous deserialization."""

import ast

from smart_linter.rules.dangerous_deserialization import DangerousDeserializationRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = DangerousDeserializationRule()
    return rule.check(tree, filename=filename)


def test_detects_pickle_loads():
    code = """
import pickle
data = pickle.loads(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "SEC003"
    assert "pickle.loads" in violations[0].message


def test_detects_pickle_load():
    code = """
import pickle
data = pickle.load(file_obj)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "pickle.load" in violations[0].message


def test_detects_marshal_loads():
    code = """
import marshal
data = marshal.loads(raw)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "marshal.loads" in violations[0].message


def test_detects_yaml_load_no_loader():
    code = """
import yaml
data = yaml.load(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "yaml.load" in violations[0].message


def test_detects_yaml_load_unsafe_loader():
    code = """
import yaml
data = yaml.load(user_input, Loader=yaml.Loader)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "yaml.load" in violations[0].message


def test_no_violation_yaml_safe_load():
    code = """
import yaml
data = yaml.safe_load(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_yaml_safe_loader():
    code = """
import yaml
data = yaml.load(user_input, Loader=yaml.SafeLoader)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_json_loads():
    code = """
import json
data = json.loads(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_shelve_open():
    code = """
import shelve
db = shelve.open("data")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "shelve.open" in violations[0].message


def test_detects_jsonpickle_decode():
    code = """
import jsonpickle
data = jsonpickle.decode(raw)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "jsonpickle.decode" in violations[0].message


def test_detects_yaml_full_loader():
    code = """
import yaml
data = yaml.load(user_input, Loader=yaml.FullLoader)
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_no_violation_yaml_base_loader():
    code = """
import yaml
data = yaml.load(user_input, Loader=yaml.BaseLoader)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_yaml_csafe_loader():
    code = """
import yaml
data = yaml.load(user_input, Loader=yaml.CSafeLoader)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_has_fix_suggestion():
    code = """
import pickle
data = pickle.loads(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert "json" in violations[0].fix.title.lower() or "msgpack" in violations[0].fix.title.lower()


def test_severity_is_error():
    code = """
import pickle
data = pickle.loads(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].severity.value == "error"


def test_multiple_dangerous_calls_detected():
    code = """
import pickle
import marshal
a = pickle.loads(data)
b = marshal.loads(data)
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_should_check_returns_true_for_pickle():
    assert DangerousDeserializationRule.should_check("import pickle") is True


def test_should_check_returns_false_for_safe_code():
    assert DangerousDeserializationRule.should_check("import json\ndata = json.loads(x)") is False


def test_location_points_to_call():
    code = """import pickle
data = pickle.loads(user_input)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].location.row == 2


def test_no_violation_yaml_cloader():
    code = """
import yaml
data = yaml.load(user_input, Loader=yaml.CLoader)
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_marshal_load():
    code = """
import marshal
data = marshal.load(file_obj)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "marshal.load" in violations[0].message


def test_get_call_info_non_attribute():
    from smart_linter.rules.dangerous_deserialization import _get_call_info

    code = "pickle()"
    tree = ast.parse(code)
    call = tree.body[0].value
    module, func = _get_call_info(call)
    assert module is None
    assert func is None


def test_get_call_info_attribute_non_name_value():
    from smart_linter.rules.dangerous_deserialization import _get_call_info

    code = "items[0].method()"
    tree = ast.parse(code)
    call = tree.body[0].value
    module, func = _get_call_info(call)
    assert module is None
    assert func is None


def test_get_loader_name_with_attribute():
    from smart_linter.rules.dangerous_deserialization import _get_loader_name

    code = "yaml.SafeLoader"
    tree = ast.parse(code)
    attr_node = tree.body[0].value
    kw = ast.keyword(arg="Loader", value=attr_node)
    assert _get_loader_name(kw) == "SafeLoader"


def test_get_loader_name_with_name():
    from smart_linter.rules.dangerous_deserialization import _get_loader_name

    code = "SafeLoader"
    tree = ast.parse(code)
    name_node = tree.body[0].value
    kw = ast.keyword(arg="Loader", value=name_node)
    assert _get_loader_name(kw) == "SafeLoader"


def test_get_loader_name_with_non_name_non_attr():
    from smart_linter.rules.dangerous_deserialization import _get_loader_name

    kw = ast.keyword(arg="Loader", value=ast.Constant(value=42))
    assert _get_loader_name(kw) is None


def test_yaml_load_with_unknown_loader_detected():
    code = """
import yaml
data = yaml.load(user_input, Loader=SomeCustomLoader)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "yaml.load" in violations[0].message


def test_yaml_load_with_constant_loader_detected():
    code = """
import yaml
data = yaml.load(user_input, Loader=42)
"""
    violations = _check_code(code)
    assert len(violations) == 1
