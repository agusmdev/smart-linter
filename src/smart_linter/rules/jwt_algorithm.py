"""SEC006: Detect JWT decode calls without explicit algorithm specification.

Calling `jwt.decode()` without specifying the `algorithms` parameter allows
algorithm confusion attacks (CVE-2016-10555). An attacker can use the 'none'
algorithm or switch from HS256 to RS256 to forge tokens.

The fix is to always specify `algorithms=["HS256"]` (or whichever algorithms
are expected). Ruff cannot detect this because it requires understanding the
jwt library's API semantics.
"""

from __future__ import annotations

import ast
from typing import ClassVar

from smart_linter.models import (
    FixSuggestion,
    Location,
    Rule,
    Severity,
    Violation,
)

JWT_DECODE_NAMES = frozenset({"decode", "decode_complete"})
JWT_MODULES = frozenset({"jwt", "jose", "jose.jwt", "python_jwt"})


def _get_qualified_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


class JwtAlgorithmRule(Rule):
    id: ClassVar[str] = "SEC006"
    description: ClassVar[str] = (
        "JWT decoded without explicit algorithm — vulnerable to algorithm confusion attacks"
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "jwt", "vulnerability")

    @classmethod
    def should_check(cls, source: str) -> bool:
        return "jwt.decode" in source or "decode(" in source and "jwt" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []

        node_index = getattr(self, "_node_index", None)
        call_nodes = node_index.get(ast.Call, []) if node_index else []
        if not call_nodes:
            call_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

        for node in call_nodes:
            if not isinstance(node, ast.Call):
                continue

            func_name = _get_qualified_name(node.func)
            if func_name is None:
                continue

            # Check if this is a jwt.decode() call
            is_jwt_decode = False
            if func_name == "jwt.decode" or func_name == "jwt.decode_complete":
                is_jwt_decode = True
            elif func_name == "decode" and isinstance(node.func, ast.Attribute):
                # Could be from jose.jwt.decode or similar
                parent = _get_qualified_name(node.func.value)
                if parent and any(parent.endswith(mod) for mod in ("jwt", "jose.jwt")):
                    is_jwt_decode = True

            if not is_jwt_decode:
                continue

            # Check if 'algorithms' keyword is present
            has_algorithms = any(kw.arg == "algorithms" for kw in node.keywords)
            if has_algorithms:
                continue

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"JWT `decode()` call without `algorithms` parameter — "
                        f"vulnerable to algorithm confusion attacks (e.g., 'none' algorithm, "
                        f"HS256/RS256 confusion). Always specify `algorithms=['HS256']`."
                    ),
                    location=Location(
                        row=node.lineno,
                        column=node.col_offset,
                    ),
                    end_location=Location(
                        row=node.end_lineno or node.lineno,
                        column=node.end_col_offset or node.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title="Add explicit `algorithms` parameter to jwt.decode()",
                        replacement="jwt.decode(token, key, algorithms=['HS256'])",
                        explanation=(
                            "Without the `algorithms` parameter, the JWT library may accept "
                            "tokens signed with any algorithm, including 'none' (no signature). "
                            "This allows attackers to forge tokens. Always specify the expected "
                            "algorithm(s). See: https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/"
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
