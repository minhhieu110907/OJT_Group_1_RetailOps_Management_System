# T04A9E6 executor handoff

The AI HTTP orchestration layer must obtain `CurrentPrincipal` from the existing
live authentication dependency (not from request body or model arguments). The
`get_bound_tool_request` FastAPI dependency already binds to `get_current_principal`
and creates a fresh request ID and budget; inject it into the AI route and
keep the returned `BoundToolRequest` for the whole HTTP request:

```python
bound: Annotated[BoundToolRequest, Depends(get_bound_tool_request)]
# For every model tool invocation in this same request:
result = bound.executor.execute(
    session, tool_id=tool_id, arguments=model_arguments, context=bound.context
)
provider_payload = serialize_tool_result(result)  # exact bytes counted by budget
```

Never instantiate a new bound request or executor per model tool call. Never
construct `ToolContext` from model or HTTP input. The binding uses context object
identity, verifies the authenticated principal reference, and refreshes the
ACTIVE ADMIN user from the database on every call. One `ToolBudget` starts at
binding time and serializes calls under a request-local lock.
For non-HTTP orchestration, `bind_authenticated_request` accepts only a
`CurrentPrincipal` already returned by the live Auth dependency.
The immutable `Settings` fields `ai_request_deadline_seconds`,
`ai_max_tool_calls`, and `ai_max_tool_output_bytes` default to 15 seconds,
3 calls, and 32 KiB respectively; configuration may only tighten these caps.
The budget clock begins when the dependency is resolved, before model work.

The AI route/orchestrator is not implemented in this PR. Its owner must apply
AI-specific Redis rate limiting and concurrency control with fail-closed
behavior before provider work, reuse this binding for all model tool calls,
and enforce a provider timeout. The executor's lock protects budget accounting
for concurrent calls within one request; the orchestrator still owns overall
request concurrency policy.

Errors: invalid model tool/arguments -> 422; tool/output quota -> 429;
authorization -> 403; deadline, database or invalid service output -> 503.
Application deadline checks cannot forcibly cancel a synchronous DB query;
the orchestration/DB layer must enforce query and provider timeouts separately.
The `execute()` signature and `ToolResult` ABI remain unchanged.

The MySQL smoke test uses only the guarded dedicated integration fixture. Set
`RETAILOPS_TEST_DATABASE_URL` to a local `mysql+pymysql` URL for a disposable
test schema, and set `MYSQL_TEST_DATABASE`, `MYSQL_TEST_USER`, and `MYSQL_USER`
so the guard can verify that the schema/user differ from development. Never
point it at the demo database. Run `pytest -vv -x
tests/modules/ai/test_tool_executor_mysql.py`; the test creates an ADMIN only
if needed, rolls that fixture back, calls all four real read services, and
records SQL to assert no writes during tool execution. Missing configuration
is an explicit test failure, not a skip.
