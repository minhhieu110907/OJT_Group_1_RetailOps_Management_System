# T04A9E6 executor handoff

The AI HTTP orchestration layer must obtain `CurrentPrincipal` from the existing
live authentication dependency (not from request body or model arguments). The
`get_bound_tool_request` FastAPI dependency already binds to `get_current_principal`
and creates a fresh request ID and budget; use it once per HTTP request. Apply
the AI-specific Redis rate/concurrency limits with fail-closed behavior in the
orchestration layer before model work. Keep the returned `BoundToolRequest` for
the whole request:

```python
# bound: BoundToolRequest = Depends(get_bound_tool_request)
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

Errors: invalid model tool/arguments -> 422; tool/output quota -> 429;
authorization -> 403; deadline, database or invalid service output -> 503.
Application deadline checks cannot forcibly cancel a synchronous DB query;
the orchestration/DB layer must enforce query and provider timeouts separately.
The `execute()` signature and `ToolResult` ABI remain unchanged.
