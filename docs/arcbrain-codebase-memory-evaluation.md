# Arcbrain Codebase Memory MCP Evaluation

Date: 2026-05-18

## Recommendation

Do not replace Arcbrain with `codebase-memory-mcp`.

Use it as a candidate source adapter for code-repository intelligence after legal and security review. Arcbrain should remain the product brain: Salesforce metadata, operating processes, evidence, recommendations, economics, risk, and replacement plans. `codebase-memory-mcp` can help populate the code slice of that brain, but it does not model business process replacement, executive evidence, ROI, controls, or agent implementation plans.

## What It Is

`codebase-memory-mcp` is a local structural code graph engine. The public README describes a single-binary MCP server with tree-sitter parsing, code search, graph search, call paths, routes, cross-repo links, impact analysis, and an optional 3D graph UI.

Useful source references:

- README: https://github.com/DeusData/codebase-memory-mcp
- License: https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/LICENSE
- Security policy: https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/SECURITY.md
- Third-party licenses: https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/THIRD_PARTY.md

## Benchmark Run

Environment:

- Platform: Windows, local Codex worktree
- Binary: `codebase-memory-mcp` v0.6.1 Windows AMD64 release
- Install mode: manual release zip extraction only
- Agent config changes: none
- Cache isolation: `CBM_CACHE_DIR` pointed at a temp evaluation directory

Arcflare worktree benchmark:

- Repo: current isolated Arcflare worktree
- Files discovered: 442
- Index time: 760 ms
- Nodes: 8,525
- Edges: 22,103
- Largest graph labels: `Method`, `Section`, `Function`, `Variable`, `Class`, `File`, `Module`, `Route`
- Major edge types: `DEFINES`, `CALLS`, `USAGE`, `DEFINES_METHOD`, `WRITES`, `SIMILAR_TO`, `HTTP_CALLS`, `SEMANTICALLY_RELATED`, `TESTS`

Salesforce connector subproject benchmark:

- Repo: `salesforce/arcflare-oauth-connector`
- Files discovered: 6
- Index time: 76 ms
- Nodes: 60
- Edges: 56

Query checks:

- `list_projects` returned both isolated projects from the temp cache.
- `get_graph_schema` returned label and edge counts for the Arcflare graph.
- `search_graph` found Arcbrain routes, frontend types, backend schema classes, and Apex-related parser/docs nodes.
- `search_code` failed on Windows with `cannot create temp file (No such file or directory)` even after `TEMP` and `TMP` were set to an existing temp directory. Treat this as a Windows CLI reliability issue to verify before production use.

Network check:

- A fresh index run was monitored with `Get-NetTCPConnection` against the `codebase-memory-mcp` process.
- Observed network connections during indexing: 0.
- This is a best-effort local observation, not a substitute for security review.

## Fit For Arcbrain

Strong fit:

- Local codebase graph indexing.
- Route, function, class, file, and dependency extraction.
- Cross-repo graph ideas.
- Impact-analysis primitives.
- Search and trace outputs that can be normalized into Arcbrain nodes and edges.
- Apex, SOQL, and SOSL language support, which matters for Salesforce-heavy clients.

Weak fit:

- It is code-centered, not operating-model-centered.
- It does not understand org roles, manual handoffs, process economics, governance controls, customer evidence, or replacement sequencing.
- Its built-in graph UI is reference material only. Arcbrain’s visual language needs to stay executive-grade and Arcflare-native.

## Licensing And Security Notes

The top-level project license is MIT. That is favorable, but it is not the whole story.

The third-party license file lists vendored libraries, including Mongoose as dual GPLv2/commercial. That needs legal review before Arcflare ships or embeds the binary in a commercial product.

The security policy is candid that the tool reads deeply from the filesystem, writes agent configuration files when installed, and can spawn background processes. The evaluation avoided install mode and used only direct CLI calls against an isolated temp cache. Any production adoption should:

- Avoid auto-install behavior.
- Never write global agent configuration.
- Run in an isolated worker sandbox.
- Use explicit repo allowlists.
- Enforce path containment.
- Disable or separately gate any UI/server mode.
- Store indexes in tenant-scoped cache directories.
- Capture binary provenance, checksum, SBOM, and version at runtime.

## Proposed Arcbrain Adapter Shape

Do not add the provider yet. First finish legal/security review and resolve the Windows `search_code` issue.

If accepted, add:

- `CodeGraphProvider` interface with methods for indexing, graph schema, search, trace, impact, and snippet retrieval.
- `CodebaseMemoryProvider` implementation that shells out to the pinned binary in an isolated temp/cache directory.
- Output normalization into Arcbrain graph nodes:
  - `code_project`
  - `code_file`
  - `code_route`
  - `code_function`
  - `code_class`
  - `code_module`
- Output normalization into Arcbrain graph edges:
  - `defines`
  - `imports`
  - `calls`
  - `http_calls`
  - `tests`
  - `changes_with`
  - `semantically_related`
- Arcbrain-only cross-links from code nodes to Salesforce metadata, integrations, recommendations, agent packages, evidence claims, and process nodes.

The key boundary: `codebase-memory-mcp` can enrich Arcbrain’s code intelligence. Arcbrain remains responsible for the enterprise operating graph and the executive replacement answer.

