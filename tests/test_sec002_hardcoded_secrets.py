"""Tests for SEC002 rule: hardcoded secrets detection."""

import ast

from smart_linter.rules.hardcoded_secrets import HardcodedSecretsRule


def _check_code(code: str, filename: str = "test.py") -> list:
    tree = ast.parse(code)
    rule = HardcodedSecretsRule()
    return rule.check(tree, filename=filename)


def test_detects_hardcoded_password():
    code = 'password = "super_secret_123"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].rule_id == "SEC002"
    assert "password" in violations[0].message


def test_detects_api_key():
    code = 'api_key = "sk-abc123def456"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert "api_key" in violations[0].message


def test_detects_token():
    code = 'token = "ghp_xxxxxxxxxxxx"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert "token" in violations[0].message


def test_detects_database_url():
    code = 'DATABASE_URL = "postgresql://user:password@host/db"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert "DATABASE_URL" in violations[0].message


def test_no_violation_for_os_environ():
    code = 'password = os.environ["DB_PASSWORD"]'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_empty_string():
    code = 'API_KEY = ""'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_placeholder_xxx():
    code = 'secret = "xxx"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_short_value():
    code = 'password = "abc"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_non_secret_name():
    code = 'name = "John"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_aws_secret_access_key():
    code = 'aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCY"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert "aws_secret_access_key" in violations[0].message


def test_no_violation_for_underscore_prefix():
    code = '_debug_password = "test123"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_changeme_placeholder():
    code = 'secret = "changeme"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_case_insensitive_name():
    code = 'PASSWORD = "MyStr0ngP@ss!"'
    violations = _check_code(code)
    assert len(violations) == 1


def test_no_violation_for_config_get():
    code = 'api_key = config.get("API_KEY")'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_os_environ_get():
    code = 'secret_key = os.environ.get("SECRET_KEY")'
    violations = _check_code(code)
    assert len(violations) == 0


def test_violation_has_fix_suggestion():
    code = 'api_key = "sk-abc123"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].fix is not None
    assert violations[0].fix.title == "Move secret to environment variable"
    assert "os.environ" in violations[0].fix.replacement
    assert "API_KEY" in violations[0].fix.replacement


def test_severity_is_error():
    code = 'password = "super_secret_123"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].severity.value == "error"


def test_no_violation_inside_main_guard():
    code = """
if __name__ == "__main__":
    password = "local_dev_password"
"""
    violations = _check_code(code)
    assert len(violations) == 0


def test_detects_private_key():
    code = 'PRIVATE_KEY = "-----BEGIN RSA PRIVATE KEY-----MIIEpAIBAAKCAQEA"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert "PRIVATE_KEY" in violations[0].message


def test_detects_encryption_key():
    code = 'encryption_key = "a1b2c3d4e5f6g7h8"'
    violations = _check_code(code)
    assert len(violations) == 1


def test_detects_connection_string():
    code = 'connection_string = "Server=myServerAddress;Database=myDataBase;User=myUsername;Password=myPassword;"'
    violations = _check_code(code)
    assert len(violations) == 1


def test_no_violation_for_replace_me_placeholder():
    code = 'api_key = "REPLACE_ME"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_your_key_here_placeholder():
    code = 'api_key = "your_api_key_here"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_no_violation_for_insert_placeholder():
    code = 'token = "insert_token_here"'
    violations = _check_code(code)
    assert len(violations) == 0


def test_should_check_returns_false_for_clean_source():
    assert HardcodedSecretsRule.should_check("x = 1") is False


def test_should_check_returns_true_for_secret_source():
    assert HardcodedSecretsRule.should_check('password = "x"') is True


def test_multiple_secrets_in_one_file():
    code = """
password = "super_secret"
api_key = "sk-12345"
token = "ghp_abcdef123456"
"""
    violations = _check_code(code)
    assert len(violations) == 3


def test_location_points_to_assignment():
    code = 'api_key = "sk-abc123"'
    violations = _check_code(code)
    assert len(violations) == 1
    assert violations[0].location.row == 1
    assert violations[0].location.column == 0


def test_list_target_no_violation():
    code = '[password] = "secret_password_123"'
    violations = _check_code(code)
    assert len(violations) == 0
