# Smart Linter — Autoresearch Ideas

## Completed Rules (17 total)
- ASYNC001: Sync blocking calls in async FastAPI endpoints
- ASYNC003: async def without await (should use def)
- ERR001: Silent exception swallowing
- ERR002: Lost exception context (raise without from)
- FAST001: BaseHTTPMiddleware instead of pure ASGI
- LOGIC001: Always-true/false conditions
- MAIN001: Mutable class attributes
- MAIN002: Late binding closure in loops
- PERF001: String concatenation in loop
- PERF002: Unnecessary list comprehension
- PRINT002: Print in async
- RES001: Resources without context manager
- RESP001: Missing response_model on endpoint
- SEC001: SQL injection via string formatting
- SEC002: Hardcoded secrets
- SEC003: Dangerous deserialization
- SEC004: Unauthenticated mutation endpoints
- FAST001: BaseHTTPMiddleware usage

## Future Rule Ideas

### High Priority (ERROR level)
- **SEC005: Mass assignment vulnerability** — Detect `Model(**user_input.model_dump())` where ORM models might receive sensitive fields (is_superuser, is_active, etc.) from user input. Hard to detect statically without type info, but can flag `**model_dump()` in ORM constructors.
- **SEC006: Timing-unsafe password comparison** — Using `==` for password/secret comparison instead of `hmac.compare_digest()`. Would catch custom auth implementations.
- **SEC007: Missing CORS origin validation** — `allow_origins=["*"]` with `allow_credentials=True` is actually rejected by browsers. Detect this misconfiguration.
- **SEC008: JWT decode without algorithm validation** — `jwt.decode(token, key, algorithms=["HS256"])` is correct but `jwt.decode(token, key)` without algorithms is vulnerable to algorithm confusion attacks.

### Medium Priority (WARNING level)
- **ASYNC004: Sequential independent awaits** — Two `await` calls in sequence where neither depends on the other could be `asyncio.gather()`. Complex to detect reliably.
- **DB001: Database session not committed on error path** — `session.add()` followed by `session.commit()` where the commit could fail and leave the session in a dirty state. Consider try/except/rollback patterns.
- **PERF003: Redundant model_validate** — Calling `model_validate()` on data that's already the correct type.
- **FAST002: Sync dependency in async app** — FastAPI dependency declared as `def` in an async app runs in threadpool (slower than async).
- **FAST003: Missing status_code on POST creation** — POST endpoints that create resources should return 201, not default 200.
- **RESP002: Return type doesn't match response_model** — Endpoint returns `dict` but `response_model` is a Pydantic model, or vice versa.

### Low Priority (INFO level)
- **STYLE001: Missing docstring on API endpoint** — Endpoints without docstrings have poor OpenAPI documentation.
- **STYLE002: Hardcoded status codes** — Using magic numbers like 404 instead of `status.HTTP_404_NOT_FOUND`.
- **MAINT001: Overly complex endpoint** — Endpoints with high cyclomatic complexity should be refactored into services.

## Benchmark Repos
- fastapi-benchmark: `/tmp/fastapi-benchmark` (full-stack-fastapi-template, 47 Python files)
- fastapi-boiler: `/tmp/fastapi-boiler` (fastapi-boilerplate, 67 Python files)
