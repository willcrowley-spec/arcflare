# Discovery Pipeline Performance — Research Findings

Research spikes for prompt caching, DSPy optimization, stage merging, and LLM response caching.

---

## 1. Anthropic Prompt Caching

### How It Works

Anthropic caches prompt **prefixes** server-side. Add `cache_control: {"type": "ephemeral"}` on content blocks to mark breakpoints. Up to 4 breakpoints per request. Everything before the last breakpoint is cached on subsequent requests with the same prefix.

- **Cache write**: 1.25x normal input token cost (one-time)
- **Cache read**: 0.1x normal input token cost (10% — the big win)
- **TTL**: 5 minutes by default (refreshes on each hit). 1-hour TTL available with telemetry enabled.
- **Minimum cached prefix**: 1024 tokens (Sonnet/Haiku), 2048 tokens (Opus)

### LiteLLM Implementation

LiteLLM 1.82.0+ passes `cache_control` through to Anthropic natively. Format:

```python
messages = [
    {"role": "system", "content": [
        {"type": "text", "text": instructions, "cache_control": {"type": "ephemeral"}}
    ]},
    {"role": "user", "content": [
        {"type": "text", "text": org_context, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": domain_specific_content}
    ]}
]
```

Our `litellm.drop_params = True` setting is already configured correctly.

### Key Research Findings

1. **Prefix-match semantics**: Any change in the prefix invalidates all downstream cache. Stable content MUST precede volatile content. Our prompt structure (instructions → org context → domain content) already has the right ordering.

2. **No quality impact**: Prompt caching is a server-side optimization — the model sees identical input regardless of cache hit/miss. The arXiv paper "Don't Break the Cache" (2601.06007) confirms 41-80% cost reduction and 13-31% TTFT improvement across 500+ agent sessions with no quality change.

3. **Strategic placement matters**: The same paper found that naive full-context caching can paradoxically increase latency. The recommended pattern is: cache system prompts and stable context, exclude dynamic tool results. Our three-tier structure aligns with this.

4. **Structured output interaction**: First request with a new JSON schema incurs 10-30s grammar compilation delay. Subsequent requests with the same schema skip this. Since all per-domain calls within a stage use the same schema, only the first call per stage pays this cost.

### Antipatterns

- **Non-deterministic prompt assembly**: If the order of metadata objects or document chunks varies between calls, the prefix won't match. Must sort/normalize dynamic data deterministically.
- **Cache thrashing**: Interleaving different operations on the same model resets the cache. Batch all stage-2 calls together before starting stage-3.
- **Exceeding 4 breakpoints**: Only 4 `cache_control` blocks per request. Our three-tier structure uses 2, well within limits.

### Impact on Langfuse Cost Tracking

LiteLLM reports `cache_creation_input_tokens` and `cache_read_input_tokens` in the usage object. Our `langfuse_generation` update in `router.py` uses `prompt_tokens` which should still be reported. Need to verify that `litellm.cost_per_token()` handles cached token pricing correctly.

### Applicability to Our Pipeline

| Stage | Instructions (stable) | Org Context (stable across domains) | Domain Content (variable) | Cache Benefit |
|-------|----------------------|--------------------------------------|---------------------------|---------------|
| 1 | Yes | Yes | N/A (single call) | Schema compilation only |
| 2 | Yes (shared across D calls) | Yes (shared) | Per-domain metadata | High — D-1 calls get cache hits |
| 3 | Yes | N/A | Per-domain steps | Moderate — instructions cached |
| 4 | Yes | N/A | Per-domain tree | Moderate — instructions cached |
| 5 | Yes | Capped metadata (shared) | Per-domain tree | High — instructions + metadata cached |
| 6 | Yes | Yes | N/A (single call) | Schema compilation only |

**Estimated savings**: For a 4-domain org, stages 2 and 5 each make 4 calls. 3 of 4 calls get cache hits on instructions + org context. If instructions + org context = 80% of tokens, that's ~70% input token reduction on cached calls.

---

## 2. DSPy Integration

### Framework Overview

DSPy 2.6 (latest stable via `pip install dspy-ai`) is a framework for programming LM pipelines with typed signatures and automatic optimization. Built-in LiteLLM integration — uses `provider/model` format natively.

### Optimizer Selection

| Optimizer | Training Data Needed | Trials | Best For |
|-----------|---------------------|--------|----------|
| BootstrapFewShot | 10-50 labeled examples | N/A (demo generation) | Quick win — auto-generate few-shot examples |
| MIPROv2 | 200+ examples | 10-100+ (auto presets) | Joint instruction + demo optimization |
| COPRO | Any size | 10-40 | Instruction-only optimization |

**Recommendation**: Start with BootstrapFewShot for each stage (cheapest), graduate to MIPROv2 "light" preset (~10 trials) for stages where quality matters most (1, 5).

### Compatibility with Our Stack

- **LiteLLM**: DSPy uses LiteLLM internally. Our `provider/model` strings work directly.
- **Structured output**: DSPy's JSONAdapter checks `litellm.supports_response_schema()` and uses structured output when available. Compatible with our Anthropic models.
- **Prompt caching conflict**: DSPy manages its own on-disk cache and disables LiteLLM's cache. Our Anthropic prompt caching is server-side and won't conflict.
- **Pydantic**: DSPy signatures use Pydantic models. Our JSON schemas can be converted to Pydantic for DSPy compatibility.

### Integration Pattern

DSPy should be a **development-time optimization tool**, not a production runtime dependency:

1. Define DSPy Modules with Signatures matching our JSON schemas
2. Build metric function from stage 7 quality heuristics + LLM-as-judge
3. Run optimization offline (separate script/notebook)
4. Export optimized prompts → write back to DB prompt blocks
5. Production pipeline uses optimized prompts via existing `resolve_prompt_blocks`

### Practical Constraints

- **Cost of optimization**: MIPROv2 "light" = ~10 trials per stage. With 6 stages × 10 trials = 60 pipeline runs (per-stage, not end-to-end). At current costs, this is ~$30-50 per optimization cycle.
- **Training data**: We need Langfuse traces from 5-10 representative orgs. These become the training set.
- **Metric function**: Must combine stage 7 quality scores with cost. Simple weighted formula: `0.7 * quality + 0.3 * (1 - normalized_cost)`.

### Antipatterns

- **Runtime DSPy dependency**: Don't ship DSPy as a production dependency. Export optimized prompts to static storage.
- **Over-optimizing per stage**: End-to-end quality matters more than per-stage metrics. Optimize per-stage first, then validate end-to-end.
- **Ignoring cost in metric**: An optimizer that finds a prompt requiring 3x more tokens isn't an improvement.

---

## 3. Stage Merging (3+4)

### Multi-Task Structured Output Quality

Claude's structured output (GA since Jan 2026) guarantees schema compliance through constrained decoding. Combined schemas are supported and reliable — the model handles multiple output sections within a single JSON response.

### Quality Considerations

- **Task complementarity**: Enrichment (stage 3) produces triggers, touchpoints, and value data. Flow analysis (stage 4) uses that enrichment to determine sequencing. These tasks are naturally sequential — doing both in one call gives the model access to enrichment context while determining flow.
- **Schema complexity**: The combined schema adds ~50 properties vs the current separate schemas. Well within Claude's structured output capabilities (tested up to hundreds of properties in GA).
- **First-call schema compilation**: Combining reduces schema compilations from 2 to 1 per new schema. Net positive for latency.

### Risk Mitigation

- **Fallback**: Keep the separate stage 3 and stage 4 code paths available behind a feature flag. If combined quality degrades, switch back.
- **Validation**: Compare combined output against the current split output on 3-5 test orgs before shipping.

### Combined Schema Design

The combined schema merges `enriched_steps` (from stage 3) with `step_flows`, `parallel_groups`, `handoffs`, `entry_points`, `terminal_points` (from stage 4) into a single response object. The enriched_steps items gain a `sequencing` field inline.

---

## 4. LLM Response Caching

### Production Patterns

The industry standard is a two-layer cache:
1. **Exact-match**: SHA-256 hash of normalized prompt → cached response (sub-ms lookup)
2. **Semantic**: Embedding similarity for rephrased queries (not needed for our use case since prompts are assembled deterministically)

For our pipeline, **exact-match only** is sufficient — prompts are assembled from deterministic inputs (metadata + prompt templates + domain context).

### Storage: Postgres vs Redis

| Factor | Postgres | Redis |
|--------|----------|-------|
| Persistence | Survives restarts | Requires persistence config |
| Query flexibility | Full SQL (analytics, cache hit rates) | Limited |
| Latency | ~1-5ms | ~0.1ms |
| Memory | Disk-backed | Memory-bound |
| Already in stack | Yes | Yes (used for discovery status) |

**Recommendation**: Postgres table. The 1-5ms overhead is negligible compared to LLM call latency (seconds). We get persistence, analytics, and no additional infrastructure.

### Cache Key Design

```
SHA-256(normalize(full_prompt_text) + operation + model)
```

Normalization: strip whitespace, sort JSON keys in any embedded JSON. The full prompt text includes metadata, document chunks, and instructions — any change to any input automatically invalidates.

### TTL Strategy

- **Default**: 24 hours. Metadata typically syncs daily or less.
- **Explicit invalidation**: On metadata sync completion, delete cache entries for that org_id.
- **Eviction**: Cron job or DB trigger to clean expired rows weekly.

### Hash Collision Risk

SHA-256 has 2^256 possible outputs. Collision probability is negligible (~10^-38 for a billion entries). No mitigation needed beyond the hash.

### Antipatterns

- **Caching validation (stage 5)**: The validation stage is designed to catch errors. Caching it means errors found in one run persist without re-validation. Consider shorter TTL or excluding stage 5 from caching.
- **No invalidation on prompt template changes**: If someone edits prompt blocks in the UI, the cache key changes automatically (full prompt text is hashed). This is self-healing.
- **Over-caching during development**: Add a `skip_cache` flag for debugging and A/B testing.
