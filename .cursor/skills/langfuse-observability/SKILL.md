---
name: langfuse-observability
description: Langfuse integration patterns for the Arcflare platform. Reference when adding new LLM calls, API routes, background workers, or modifying observability code. Covers cost tracking, user/org attribution, scoring, and production reliability.
---

# Langfuse Observability

## When to Use

Use this skill when:
- Adding a new LLM call or embedding operation
- Creating a new API route that invokes LLM calls
- Creating a new Celery worker task
- Modifying observability, tracing, or cost tracking code
- Debugging missing traces, costs, or scores in the Langfuse dashboard
- Updating model pricing

## Architecture

### Three Layers

1. **Attribution** (`langfuse_context`) — wraps entry points (routes, workers) to propagate `user_id`, `org_id`, `session_id` to all nested observations
2. **Observations** (`langfuse_span`, `langfuse_generation`) — track pipeline stages and individual LLM calls
3. **Cost** (`compute_cost` + `usage_details` / `cost_details`) — attach token counts and USD costs to every generation

### Entry Point Pattern

Every API route or worker task that triggers LLM calls MUST wrap its top-level scope with `langfuse_context`:

```python
from app.core.observability import langfuse_context, langfuse_span

# API route
with langfuse_context(user_id=str(user.id), org_id=str(org_id), session_id=str(thread_id)):
    with langfuse_span("operation_name", metadata={...}) as span:
        # All LLM calls inside here automatically inherit user/org/session
        result = llm_call(...)

# Celery worker (no user_id)
with langfuse_context(org_id=org_id, session_id=str(run_id)):
    with langfuse_span("worker_name", metadata={...}):
        asyncio.run(_pipeline())
```

### Generation Pattern

Every `gen.update()` call MUST use `usage_details` + `cost_details` (v3 format):

```python
from app.core.model_prices import compute_cost
from app.core.observability import langfuse_generation

with langfuse_generation("operation_name", model=model) as gen:
    result = call_llm(...)
    if gen:
        gen.update(
            output=result.text,
            usage_details={
                "input": result.input_tokens,
                "output": result.output_tokens,
            },
            cost_details=compute_cost(model, result.input_tokens, result.output_tokens),
        )
```

### Score Pattern

Post numeric quality metrics to the current trace:

```python
from app.core.observability import langfuse_score

langfuse_score(name="metric_name", value=0.85, comment="optional context")
```

Must be called inside an active span/generation context.

## Rules

### MUST Do
- Wrap every entry point (route, worker) with `langfuse_context(user_id, org_id, session_id)`
- Pass `usage_details` + `cost_details` on every `gen.update()` call
- Call `flush_langfuse()` in the `finally` block of every Celery task
- Use `langfuse_span` for pipeline stages, `langfuse_generation` for LLM calls
- Keep spans open for the full duration of the work they represent

### MUST NOT Do
- Pass fake token counts (e.g., `usage={"total": 1}`)
- Use the legacy `usage={"input": ..., "output": ..., "total": ...}` format
- Open a span just to grab a trace ID and immediately close it before the LLM call
- Skip `langfuse_context` on entry points (breaks user/org attribution)
- Hardcode model prices inline — always use `compute_cost()` from `model_prices.py`

## Model Price Table

Located in `backend/app/core/model_prices.py`. Contains USD-per-token prices for each model.

### Updating Prices
1. Edit `MODEL_PRICES` dict in `model_prices.py`
2. Also update the model definition in Langfuse Cloud project settings (belt and suspenders)
3. Price changes only affect new traces — historical data retains original costs

### Adding a New Model
1. Add entry to `MODEL_PRICES` with `{"input": price_per_token, "output": price_per_token}`
2. Register model definition in Langfuse Cloud
3. Ensure the model string in `MODEL_PRICES` matches exactly what `_resolve_model()` returns

## Antipatterns

| Antipattern | Why It's Bad | Fix |
|-------------|-------------|-----|
| `usage={"total": 1}` | Fake data, costs show $0 | Estimate tokens from content length (÷4) |
| Short-lived span for trace ID | LLM work runs outside span, invisible | Keep span open for full operation |
| Missing `langfuse_context` | No user/org on traces, can't attribute costs | Wrap entry point |
| `flush_langfuse()` missing from worker | Traces may be lost | Add to `finally` block |
| Hardcoded `cost_details` | Prices change, gets stale | Use `compute_cost()` |
| Streaming without generation | Chat costs invisible | Post generation after stream completes |

## Files Reference

| File | Purpose |
|------|---------|
| `backend/app/core/observability.py` | `langfuse_context`, `langfuse_span`, `langfuse_generation`, `langfuse_score`, `flush_langfuse`, `shutdown_langfuse` |
| `backend/app/core/model_prices.py` | `MODEL_PRICES` dict, `compute_cost()` |
| `backend/app/services/ai/router.py` | `llm_call()` — central generation with cost tracking |
| `backend/app/main.py` | FastAPI lifespan with `shutdown_langfuse()` |
