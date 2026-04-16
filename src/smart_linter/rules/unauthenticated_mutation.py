"""SEC004: Detect mutation endpoints (POST/PUT/DELETE/PATCH) without authentication dependencies.

Flags FastAPI endpoints that modify data but don't require any form of
authentication, which is a common security oversight. Ruff cannot detect this
because it requires understanding FastAPI's dependency injection system.
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

MUTATION_METHODS = frozenset({"post", "put", "delete", "patch"})

# Known auth-related dependency name substrings (matched via `in` check)
AUTH_DEPENDENCY_SUBSTRINGS = frozenset({
    "get_current_user",
    "get_current_active_user",
    "get_current_active_superuser",
    "get_current_superuser",
    "get_current_verified_user",
    "current_user",
    "get_user",
    "require_auth",
    "require_user",
    "verify_token",
    "validate_token",
    "check_auth",
    "authenticate",
    "oauth2_scheme",
    "get_api_key",
    "validate_api_key",
})

# Auth-related type annotation names
AUTH_TYPE_NAMES = frozenset({
    "CurrentUser",
    "TokenDep",
    "AuthenticatedUser",
    "UserDep",
    "AuthDep",
})

# Endpoint names that are intentionally public (login, signup, health, etc.)
PUBLIC_ENDPOINT_PATTERNS = frozenset({
    "login",
    "signup",
    "register",
    "sign_up",
    "sign_in",
    "log_in",
    "log_in_access_token",
    "login_access_token",
    "access_token",
    "refresh_access_token",
    "refresh",
    "password_recovery",
    "recover_password",
    "reset_password",
    "forgot_password",
    "verify_email",
    "confirm_email",
    "health_check",
    "health",
    "ping",
    "readiness",
    "liveness",
    "webhook",
    "callback",
    "stripe_webhook",
    "github_webhook",
    "payment_webhook",
    "send_email",
    "test_email",
})

# URL path segments that indicate public endpoints
PUBLIC_PATH_SEGMENTS = frozenset({
    "login",
    "signup",
    "register",
    "sign-up",
    "sign-in",
    "log-in",
    "password-recovery",
    "reset-password",
    "forgot-password",
    "verify-email",
    "confirm-email",
    "health",
    "ping",
    "webhook",
    "callback",
    "public",
})


def _get_qualified_name(node: ast.expr) -> str | None:
    """Return dotted name for Name/Attribute nodes."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        value = _get_qualified_name(node.value)
        if value is not None:
            return f"{value}.{node.attr}"
    return None


def _extract_decorator_method(decorator: ast.expr) -> str | None:
    """Extract HTTP method from decorator like @router.post(...)."""
    if isinstance(decorator, ast.Call):
        func = decorator.func
    elif isinstance(decorator, ast.Attribute):
        func = decorator
    else:
        return None

    if isinstance(func, ast.Attribute):
        return func.attr.lower() if func.attr.lower() in MUTATION_METHODS else None
    return None


def _extract_path_from_decorator(decorator: ast.expr) -> str:
    """Extract URL path from decorator like @router.post('/items/{id}')."""
    if isinstance(decorator, ast.Call) and decorator.args:
        first_arg = decorator.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            return first_arg.value
    return ""


def _has_dependencies_kwarg(decorator: ast.expr) -> list[str]:
    """Extract dependency names from dependencies=[Depends(...)] in decorator.

    Returns the inner names, e.g. for `dependencies=[Depends(get_current_user)]`
    returns ["get_current_user"].
    """
    deps: list[str] = []
    if not isinstance(decorator, ast.Call):
        return deps
    for kw in decorator.keywords:
        if kw.arg == "dependencies" and isinstance(kw.value, ast.List):
            for elt in kw.value.elts:
                if isinstance(elt, ast.Call):
                    # Depends(get_current_user) → extract get_current_user
                    if elt.args:
                        name = _get_qualified_name(elt.args[0])
                        if name:
                            deps.append(name)
                    # Also check the function name itself
                    func_name = _get_qualified_name(elt.func)
                    if func_name:
                        deps.append(func_name)
                elif isinstance(elt, ast.Name):
                    deps.append(elt.id)
    return deps


def _get_param_names_and_types(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[list[str], list[str]]:
    """Extract parameter names and their type annotation names."""
    param_names: list[str] = []
    type_names: list[str] = []
    for arg in func.args.args:
        param_names.append(arg.arg)
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                type_names.append(arg.annotation.id)
            elif isinstance(arg.annotation, ast.Subscript):
                if isinstance(arg.annotation.value, ast.Name):
                    type_names.append(arg.annotation.value.id)
    for arg in func.args.posonlyargs:
        param_names.append(arg.arg)
    for arg in func.args.kwonlyargs:
        param_names.append(arg.arg)
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                type_names.append(arg.annotation.id)
            elif isinstance(arg.annotation, ast.Subscript):
                if isinstance(arg.annotation.value, ast.Name):
                    type_names.append(arg.annotation.value.id)
    # Check defaults for Depends()
    for default in func.args.defaults + func.args.kw_defaults:
        if default and isinstance(default, ast.Call):
            name = _get_qualified_name(default.func)
            if name:
                type_names.append(name)
    return param_names, type_names


def _has_auth_dependency(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    decorators: list[ast.expr],
) -> bool:
    """Check if the endpoint has any authentication dependency."""
    # Check decorator-level dependencies
    for dec in decorators:
        dep_names = _has_dependencies_kwarg(dec)
        for dep in dep_names:
            dep_lower = dep.lower()
            for auth in AUTH_DEPENDENCY_SUBSTRINGS:
                if auth in dep_lower:
                    return True

    # Check function parameters
    param_names, type_names = _get_param_names_and_types(func)

    # Check parameter names for auth hints
    for pname in param_names:
        pname_lower = pname.lower()
        if any(auth in pname_lower for auth in ("current_user", "token", "auth", "api_key")):
            return True

    # Check type annotations for auth types
    for tname in type_names:
        if tname in AUTH_TYPE_NAMES:
            return True
        tname_lower = tname.lower()
        if any(auth in tname_lower for auth in AUTH_DEPENDENCY_SUBSTRINGS):
            return True

    return False


def _is_public_endpoint(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    decorators: list[ast.expr],
) -> bool:
    """Check if the endpoint name or path suggests it's intentionally public."""
    # Check function name
    func_name = func.name.lower().replace("-", "_")
    for pattern in PUBLIC_ENDPOINT_PATTERNS:
        if pattern in func_name:
            return True

    # Check URL paths from decorators
    for dec in decorators:
        path = _extract_path_from_decorator(dec)
        path_lower = path.lower()
        for segment in PUBLIC_PATH_SEGMENTS:
            if segment in path_lower:
                return True

    return False


class UnauthenticatedMutationRule(Rule):
    id: ClassVar[str] = "SEC004"
    description: ClassVar[str] = (
        "Mutation endpoint (POST/PUT/DELETE/PATCH) has no authentication dependency"
    )
    severity: ClassVar[Severity] = Severity.ERROR
    tags: ClassVar[tuple[str, ...]] = ("security", "authentication", "fastapi")

    @classmethod
    def should_check(cls, source: str) -> bool:
        # Only check files that have FastAPI endpoint decorators
        has_decorator = any(
            f"@{prefix}.{method}" in source
            for prefix in ("app", "router")
            for method in MUTATION_METHODS
        )
        if not has_decorator:
            has_decorator = any(
                f"@{prefix}.{method}" in source
                for prefix in ("router", "api_router", "app")
                for method in MUTATION_METHODS
            )
        return has_decorator or "APIRouter" in source or "FastAPI" in source

    def check(self, tree: ast.AST, filename: str = "") -> list[Violation]:
        violations: list[Violation] = []
        parent_map = getattr(self, "_parent_map", {})

        node_index = getattr(self, "_node_index", None)
        func_nodes = []
        if node_index:
            func_nodes.extend(node_index.get(ast.FunctionDef, []))
            func_nodes.extend(node_index.get(ast.AsyncFunctionDef, []))
        if not func_nodes:
            func_nodes = [
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

        for func in func_nodes:
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # Find mutation decorators
            mutation_dec = None
            method = None
            for dec in func.decorator_list:
                m = _extract_decorator_method(dec)
                if m:
                    mutation_dec = dec
                    method = m
                    break

            if mutation_dec is None or method is None:
                continue

            # Skip known public endpoints
            if _is_public_endpoint(func, func.decorator_list):
                continue

            # Check for auth
            if _has_auth_dependency(func, func.decorator_list):
                continue

            # Build a descriptive path
            path = _extract_path_from_decorator(mutation_dec)
            method_upper = method.upper()
            endpoint_desc = f"{method_upper} `{path}`" if path else method_upper
            message = (
                f"Unauthenticated mutation endpoint: `{func.name}` ({endpoint_desc}) "
                f"has no authentication dependency. "
                f"Add `Depends(get_current_user)` or similar to protect this endpoint."
            )

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=message,
                    location=Location(
                        row=func.lineno,
                        column=func.col_offset,
                    ),
                    end_location=Location(
                        row=func.end_lineno or func.lineno,
                        column=func.end_col_offset or func.col_offset,
                    ),
                    severity=self.severity,
                    fix=FixSuggestion(
                        title=f"Add authentication dependency to `{func.name}`",
                        replacement=(
                            f"Add `current_user: CurrentUser` parameter or "
                            f"`dependencies=[Depends(get_current_user)]` to the decorator"
                        ),
                        explanation=(
                            "Mutation endpoints without authentication allow anyone to modify data. "
                            "Add a dependency that validates the user's identity (e.g. JWT token, "
                            "API key, session cookie). Even if this is intentionally public, "
                            "explicitly document it with a comment."
                        ),
                    ),
                    filename=filename,
                )
            )

        return violations
