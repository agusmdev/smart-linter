"""Tests for RES001 rule: unclosed resource detection."""

import ast

from smart_linter.rules.unclosed_resource import UnclosedResourceRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = UnclosedResourceRule()
    return rule.check(tree, filename=filename)


def test_detects_open_without_with():
    code = """
f = open("data.txt")
content = f.read()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "RES001"
    assert "open" in violations[0].message


def test_no_detection_for_with_open():
    code = """
with open("data.txt") as f:
    content = f.read()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_detection_when_returned():
    code = """
def get_file():
    f = open("data.txt")
    return f
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_detection_when_used_in_with():
    code = """
f = open("data.txt")
with f:
    content = f.read()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_httpx_client_without_with():
    code = """
import httpx
client = httpx.Client()
response = client.get("https://example.com")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "httpx.Client" in violations[0].message


def test_no_detection_for_with_httpx_client():
    code = """
import httpx
with httpx.Client() as client:
    response = client.get("https://example.com")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_detection_when_closed_in_finally():
    code = """
f = open("data.txt")
try:
    content = f.read()
finally:
    f.close()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_open_in_function_no_safety():
    code = """
def read_data():
    f = open("data.txt")
    content = f.read()
    return content
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "open" in violations[0].message


def test_no_detection_when_yielded():
    code = """
def gen():
    f = open("data.txt")
    yield f
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_subprocess_popen_without_context():
    code = """
import subprocess
p = subprocess.Popen(["echo", "hi"])
p.wait()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "subprocess.Popen" in violations[0].message


def test_detects_httpx_async_client_without_with():
    code = """
import httpx
client = httpx.AsyncClient()
response = await client.get("https://example.com")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "httpx.AsyncClient" in violations[0].message


def test_detects_socket_without_with():
    code = """
import socket
s = socket.socket()
s.connect(("localhost", 8080))
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "socket.socket" in violations[0].message


def test_detects_sqlite3_connect_without_with():
    code = """
import sqlite3
conn = sqlite3.connect("db.sqlite")
cursor = conn.cursor()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "sqlite3.connect" in violations[0].message


def test_detects_redis_without_with():
    code = """
import redis
r = redis.Redis()
r.get("key")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "redis.Redis" in violations[0].message


def test_no_detection_for_non_resource_call():
    code = """
x = int("42")
y = list()
z = dict()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_detection_for_with_subprocess_popen():
    code = """
import subprocess
with subprocess.Popen(["echo", "hi"]) as p:
    p.wait()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_fix_suggestion_present():
    code = """
f = open("data.txt")
content = f.read()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    fix = violations[0].fix
    assert fix is not None
    assert "with" in fix.replacement
    assert "with" in fix.title.lower()
    assert fix.explanation is not None


def test_detects_urlopen_without_with():
    code = """
import urllib.request
resp = urllib.request.urlopen("https://example.com")
data = resp.read()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "urlopen" in violations[0].message


def test_detects_psycopg2_without_with():
    code = """
import psycopg2
conn = psycopg2.connect("dbname=test")
cursor = conn.cursor()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "psycopg2.connect" in violations[0].message


def test_no_detection_yield_from():
    code = """
def gen():
    import httpx
    client = httpx.Client()
    yield client
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_mysql_connector():
    code = """
import mysql.connector
conn = mysql.connector.connect(host="localhost")
cursor = conn.cursor()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "mysql.connector.connect" in violations[0].message


def test_detects_strict_redis():
    code = """
import redis
r = redis.StrictRedis()
r.get("key")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "redis.StrictRedis" in violations[0].message


def test_multiple_violations_in_same_function():
    code = """
def process():
    f = open("a.txt")
    g = open("b.txt")
    return f.read() + g.read()
"""
    violations = _check_code(code)
    assert len(violations) == 2


def test_violation_location_correct():
    code = """
f = open("data.txt")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].location.row == 2
    assert violations[0].location.column == 0


def test_open_attr_call_on_open_module():
    code = """
x = open.read()
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "open" in violations[0].message


def test_non_resource_attribute_call():
    code = """
x = something.random()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_find_enclosing_body_function():
    from smart_linter.rules.unclosed_resource import _find_enclosing_body

    code = """
def foo():
    pass
"""
    tree = ast.parse(code)
    func = tree.body[0]
    parent_map = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    result = _find_enclosing_body(func.body[0], parent_map)
    assert result is func.body


def test_find_enclosing_body_class():
    from smart_linter.rules.unclosed_resource import _find_enclosing_body

    code = """
class Foo:
    pass
"""
    tree = ast.parse(code)
    cls = tree.body[0]
    parent_map = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    result = _find_enclosing_body(cls.body[0], parent_map)
    assert result is cls.body


def test_find_enclosing_body_module():
    from smart_linter.rules.unclosed_resource import _find_enclosing_body

    code = """x = 1"""
    tree = ast.parse(code)
    node = tree.body[0]
    parent_map = {node: tree}
    result = _find_enclosing_body(node, parent_map)
    assert result is None


def test_find_enclosing_body_traverses_up():
    from smart_linter.rules.unclosed_resource import _find_enclosing_body

    code = """
def foo():
    if True:
        pass
"""
    tree = ast.parse(code)
    func = tree.body[0]
    if_stmt = func.body[0]
    parent_map = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_map[child] = parent
    result = _find_enclosing_body(if_stmt, parent_map)
    assert result is func.body


def test_get_module_body():
    from smart_linter.rules.unclosed_resource import _get_module_body

    tree = ast.parse("x = 1\ny = 2")
    assert _get_module_body(tree) == tree.body


def test_is_inside_with_context_returns_true():
    from smart_linter.rules.unclosed_resource import _is_inside_with_context

    code = """with open("data.txt") as f:\n    pass"""
    tree = ast.parse(code)
    with_node = tree.body[0]
    call = with_node.items[0].context_expr
    assign = ast.Assign(targets=[ast.Name(id="f")], value=call)
    parent_map = {id(assign): with_node}
    parent_map_real = {assign: with_node}
    assert _is_inside_with_context(assign, parent_map_real) is True


def test_subscript_target_no_violation():
    code = """
items = {}
items[0] = open("data.txt")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_nested_scope_in_if():
    code = """
f = open("data.txt")
if True:
    def inner():
        pass
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_yield_from_safe():
    code = """
def gen():
    f = open("data.txt")
    yield from f
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_trystar_finally_close():
    code = """
f = open("data.txt")
try:
    pass
except* Exception:
    pass
finally:
    f.close()
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_should_check_various_hints():
    assert UnclosedResourceRule.should_check("x = AsyncClient()") is True
    assert UnclosedResourceRule.should_check("x = urlopen(") is True
    assert UnclosedResourceRule.should_check("x = Popen(") is True
    assert UnclosedResourceRule.should_check("x = socket(") is True
    assert UnclosedResourceRule.should_check("x = StrictRedis()") is True
    assert UnclosedResourceRule.should_check("x = connect(") is True
    assert UnclosedResourceRule.should_check("x = 42") is False


def test_class_body_resource():
    code = """
class Handler:
    f = open("data.txt")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "open" in violations[0].message
