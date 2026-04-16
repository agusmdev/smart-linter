"""Tests for SEC001 rule: SQL injection via string formatting."""

import ast

from smart_linter.rules.sql_injection import SqlInjectionRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = SqlInjectionRule()
    return rule.check(tree, filename=filename)


def test_detects_fstring_in_execute():
    code = """
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "SEC001"
    assert "f-string" in violations[0].message


def test_detects_percent_format_in_execute():
    code = """
cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "% formatting" in violations[0].message


def test_detects_format_method_in_execute():
    code = """
cursor.execute("SELECT * FROM users WHERE id = {}".format(user_id))
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert ".format()" in violations[0].message


def test_detects_concatenation_with_sql_keyword():
    code = """
cursor.execute("SELECT * FROM users WHERE id = " + user_id)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "string concatenation" in violations[0].message


def test_no_violation_for_parameterized_query():
    code = """
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_plain_string_no_formatting():
    code = """
cursor.execute("SELECT * FROM users")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_fstring_in_non_execute():
    code = """
result = f"SELECT * FROM users WHERE id = {user_id}"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_executemany_with_fstring():
    code = """
cursor.executemany(f"INSERT INTO users (name) VALUES ('{name}')", rows)
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "executemany" in violations[0].message


def test_no_violation_for_non_sql_string_formatting():
    code = """
cursor.execute(f"Hello {name}")
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_multiple_sql_keywords_detected_once():
    code = """
cursor.execute(f"SELECT * FROM users WHERE id = {user_id} UNION SELECT * FROM admins")
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_detects_insert_with_format_method():
    code = """
cursor.execute("INSERT INTO users (name) VALUES ('{}')".format(name))
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert ".format()" in violations[0].message


def test_detects_update_with_percent_format():
    code = """
cursor.execute("UPDATE users SET name = '%s' WHERE id = %s" % (name, uid))
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "% formatting" in violations[0].message


def test_detects_delete_with_concatenation():
    code = """
cursor.execute("DELETE FROM users WHERE id = " + user_id)
"""
    violations = _check_code(code)
    assert len(violations) == 1


def test_violation_has_fix_suggestion():
    code = """
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert violations[0].fix.title == "Use parameterized query instead of string formatting"
    assert violations[0].fix.replacement is not None
    assert "%s" in violations[0].fix.replacement
    assert "parameterized" in violations[0].fix.explanation.lower()


def test_severity_is_error():
    code = """
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].severity.value == "error"


def test_no_violation_parameterized_question_mark():
    code = """
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_parameterized_named():
    code = """
cursor.execute("SELECT * FROM users WHERE id = :id", {"id": user_id})
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_drop_with_fstring():
    code = """
cursor.execute(f"DROP TABLE {table_name}")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert "f-string" in violations[0].message


def test_location_points_to_execute_call():
    code = """\
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].location.row == 1
    assert violations[0].location.column == 0


def test_migration_file_revisions_path_excluded():
    code = """
conn.execute(f"update dispatch_core.organization set slug = '{slug}' where id = {r[0]}")
"""
    violations = _check_code(code, filename="/database/revisions/core/versions/2021-07-22_c0bc938b058e.py")
    assert len(violations) == 0


def test_migration_file_migrations_path_excluded():
    code = """
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    violations = _check_code(code, filename="/migrations/001_initial.py")
    assert len(violations) == 0


def test_migration_file_alembic_path_excluded():
    code = """
conn.execute(f"update dispatch_core.organization set slug = '{slug}' where id = {r[0]}")
"""
    violations = _check_code(code, filename="/alembic/versions/abc123.py")
    assert len(violations) == 0


def test_normal_file_still_detected_with_migration_exclusion():
    code = """
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    violations = _check_code(code, filename="src/api.py")
    assert len(violations) == 1
    assert violations[0].rule_id == "SEC001"


def test_execute_no_args():
    code = "cursor.execute()"
    violations = _check_code(code)
    assert len(violations) == 0


def test_execute_parameterized_with_format():
    code = """
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_describe_format_type_fallback():
    from smart_linter.rules.sql_injection import _describe_format_type

    assert _describe_format_type(ast.Constant(value=42)) == "string formatting"
