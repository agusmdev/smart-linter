# Smart Linter — Autoresearch Ideas

## Completed Rules (21 total)
See CLAUDE.md for full list. New rules added in this session:
- SEC004: Unauthenticated mutation endpoints (ERROR) — 67 findings on dispatch
- RESP001: Missing response_model on API endpoint (WARNING) — 35 findings on dispatch
- ASYNC003: async def without await (WARNING) — 21 findings total
- ERR002: Lost exception context (WARNING) — 1 finding
- FAST001: BaseHTTPMiddleware usage (WARNING) — 4 findings
- SEC005: Mass assignment via **model_dump() (ERROR) — 16 findings on dispatch
- SEC006: JWT decode without algorithm (ERROR) — 3 findings on dispatch
- SEC007: CORS misconfiguration (ERROR) — 0 findings on benchmarks
- FAST002: POST creation without status_code=201 (INFO) — 63 findings total

## Future Rule Ideas

### High Priority (ERROR level)
- **SEC008: Timing-unsafe password comparison** — Using `==` for password/secret comparison instead of `hmac.compare_digest()`. Would catch custom auth implementations.
- **SEC009: Insecure cookie settings** — Session cookies without `httponly=True`, `secure=True`, or `samesite` attribute.

### Medium Priority (WARNING level)
- **ASYNC004: Sequential independent awaits** — Two `await` calls in sequence where neither depends on the other could be `asyncio.gather()`. Complex to detect reliably.
- **DB001: DB session.add() without commit in code path** — Detect paths where session.add() is called but session.commit() is not reachable.
- **FAST003: sync def endpoint in async-only app** — Regular `def` endpoints run in threadpool. When the app uses AsyncSession everywhere, sync endpoints indicate a mismatch.
- **RESP002: Return type doesn't match response_model** — Endpoint returns `dict` but `response_model` is a Pydantic model, or vice versa.

### Low Priority (INFO level)
- **STYLE001: Missing docstring on API endpoint** — Endpoints without docstrings have poor OpenAPI documentation.
- **STYLE002: Hardcoded status codes** — Using magic numbers like 404 instead of `status.HTTP_404_NOT_FOUND`.

## Benchmark Repos
- fastapi-benchmark: `/tmp/fastapi-benchmark` (full-stack-fastapi-template, 47 Python files)
- fastapi-boiler: `/tmp/fastapi-boiler` (fastapi-boilerplate, 67 Python files)
- dispatch-bench: `/tmp/dispatch-bench` (Netflix Dispatch, 717 Python files)
