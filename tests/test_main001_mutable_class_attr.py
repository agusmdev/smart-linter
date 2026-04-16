"""Tests for MAIN001 rule: mutable class attribute shared across all instances."""

import ast

from smart_linter.rules.mutable_class_attr import MutableClassAttrRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = MutableClassAttrRule()
    return rule.check(tree, filename=filename)


def test_detects_empty_list():
    code = """
class X:
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "MAIN001"
    assert "items" in violations[0].message


def test_detects_empty_dict():
    code = """
class X:
    items = {}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_detects_set_constructor():
    code = """
class X:
    items = set()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_detects_dict_literal_with_items():
    code = """
class X:
    items = {"a": 1}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_no_violation_for_int():
    code = """
class X:
    COUNT = 0
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_tuple():
    code = """
class X:
    TAGS = ("a", "b")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_with_slots():
    code = """
class X:
    __slots__ = ("items",)
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_annotation_only():
    code = """
class X:
    items: list
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_init_assignment():
    code = """
class X:
    def __init__(self):
        self.items = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_list_constructor():
    code = """
class X:
    items = list()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_detects_defaultdict_constructor():
    code = """
class X:
    items = defaultdict(list)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_multiple_mutable_attrs_detected_separately():
    code = """
class X:
    items = []
    config = {}
    cache = set()
"""
    violations = _check_code(code)
    assert len(violations) == 3
    names = [v.message for v in violations]
    assert any("items" in m for m in names)
    assert any("config" in m for m in names)
    assert any("cache" in m for m in names)


def test_no_violation_for_string():
    code = """
class X:
    HOST = "localhost"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_float():
    code = """
class X:
    RATE = 1.5
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_bool():
    code = """
class X:
    DEBUG = True
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_none():
    code = """
class X:
    instance = None
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_frozenset():
    code = """
class X:
    ALLOWED = frozenset({"a", "b"})
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_ordered_dict_constructor():
    code = """
class X:
    items = OrderedDict()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_detects_collections_dot_defaultdict():
    code = """
class X:
    items = collections.defaultdict(list)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_detects_list_with_elements():
    code = """
class X:
    items = [1, 2, 3]
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_detects_set_literal():
    code = """
class X:
    items = {1, 2}
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_violation_has_fix_suggestion():
    code = """
class X:
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert fix.title is not None
    assert "__init__" in fix.title
    assert fix.replacement is not None
    assert "self.items" in fix.replacement
    assert fix.explanation is not None
    assert "shared" in fix.explanation.lower()


def test_annotated_assign_in_plain_class_detected():
    code = """
class X:
    items: list = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_annotated_assign_with_base_not_flagged():
    """Annotated attrs with defaults in classes with base classes are Pydantic/dataclass patterns."""
    code = """
class X(SomeBase):
    items: list = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_nested_class_detected():
    code = """
class Outer:
    class Inner:
        items = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_multiple_classes_detected_independently():
    code = """
class A:
    items = []

class B:
    config = {}
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_should_check_skips_no_class():
    assert not MutableClassAttrRule.should_check("x = 1")


def test_should_check_passes_with_class():
    assert MutableClassAttrRule.should_check("class Foo: pass")


def test_no_violation_for_dict_constructor():
    code = """
class X:
    items = dict()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_pydantic_basemodel_subclass_not_detected():
    code = """
class CaseRead(BaseModel):
    items: list = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_pydantic_dotted_basemodel_not_detected():
    code = """
class Foo(pydantic.BaseModel):
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_dataclass_decorator_not_detected():
    code = """
@dataclass
class Config:
    tags = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_dataclass_call_decorator_not_detected():
    code = """
@dataclass(frozen=True)
class Config:
    tags = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_sqlalchemy_base_not_detected():
    code = """
class User(Base):
    roles = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_sqlalchemy_declarative_base_not_detected():
    code = """
class User(DeclarativeBase):
    roles = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_plain_class_still_detected():
    code = """
class X:
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_custom_base_still_detected():
    code = """
class Foo(MyCustomBase):
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "items" in violations[0].message


def test_pydantic_schema_subclass_not_detected():
    code = """
class MySchema(Schema):
    data = {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_pydantic_base_settings_not_detected():
    code = """
class AppSettings(BaseSettings):
    defaults = {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_sqlalchemy_model_not_detected():
    code = """
class User(Model):
    permissions = set()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_mixed_classes_detected_independently():
    code = """
class PydanticModel(BaseModel):
    items = []

class PlainClass:
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "PlainClass" in violations[0].filename or "items" in violations[0].message


def test_dataclass_attribute_decorator():
    code = """
@dataclasses.dataclass
class Config:
    tags = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_dataclass_attribute_call_decorator():
    code = """
@dataclasses.dataclass(frozen=True)
class Config:
    tags = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_slots_via_annotation():
    code = """
class X:
    __slots__: tuple
    items = []
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_non_name_target_no_violation():
    code = """
class X:
    a, b = [], {}
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_underscore_prefix_no_violation():
    code = """
class X:
    _items = []
"""
    violations = _check_code(code)
    assert len(violations) == 0
