# Domain Process Map — Hierarchical Compound Graph View

**Date:** 2026-04-18
**Status:** Draft (pending industry research validation)
**Approach:** ELK layout engine + React Flow rendering

## Problem

The current process map shows only direct children of whichever process you open. Each child has its own "Open Process Map" link, forcing the user to drill through multiple levels to understand the end-to-end flow. There is no single view that shows a full domain's process hierarchy — containers, sub-processes, and leaf steps — in one canvas.

## Solution

Replace the per-process map with a single **domain-level compound graph**. When a user opens a domain's process map, they see:

- **Leaf steps** as individual cards (the existing `ProcessNodeComponent` design).
- **Intermediate processes** as labeled containers that wrap their children.
- **Containers nest recursively** to match the process hierarchy (variable depth, 2–4+ levels).
- **Edges** between steps render regardless of which containers they sit in.
- **Gaps** retain the existing red edge + warning icon treatment.

The "Open Process Map" link is removed from non-domain processes. Only domains get the link.

## Data & API

### New endpoint

`GET /api/v1/processes/{domain_id}/domain-graph`

Returns the full recursive hierarchy and all connections for a domain:

```json
{
  "domain": { "id": "...", "name": "..." },
  "hierarchy": [
    {
      "id": "...",
      "name": "...",
      "parent_id": "...",
      "level": "process",
      "status": "discovered",
      "confidence_score": 0.87,
      "needs_review": false,
      "is_leaf": false,
      "leaf_count": 12,
      "children": [
        { "id": "...", "name": "...", "is_leaf": true, "leaf_count": 0, "children": [] }
      ]
    }
  ],
  "edges": [
    {
      "id": "...",
      "source_id": "...",
      "target_id": "...",
      "label": "handoff",
      "description": "...",
      "is_gap": false
    }
  ]
}
```

- `hierarchy`: recursive tree of all processes under the domain. `is_leaf` = true for processes with no children (these become step cards). `leaf_count` = total leaf descendants (used for collapsed container badges). `status`, `confidence_score`, `needs_review` included for future in-map review features.
- `edges`: union of `ProcessEdge` rows and `ProcessHandoff` rows scoped to the domain's subtree. Gap metadata preserved.
- The existing `GET /processes/{id}` endpoint and its `graph` field are unchanged.

### Org settings additions

Two new columns on the organization model:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `process_map_direction` | `"LR"` \| `"TB"` | `"TB"` | Flow direction: left-to-right or top-to-bottom |
| `process_map_default_state` | `"expanded"` \| `"collapsed"` | `"collapsed"` | Whether top-level containers start expanded or collapsed |

Exposed via the existing org settings API and editable on the Organization settings page.

## Layout Engine (ELK)

### Integration

A new frontend module (`frontend/src/lib/elkLayout.ts`) takes the domain-graph API response and produces React Flow-ready nodes and edges.

**Pipeline:**

1. Build an ELK graph from the hierarchy — each non-leaf process becomes a **compound node** (container), each leaf becomes a **terminal node** (step card). Edges map 1:1.
2. Pass the ELK graph through `elkjs` with the org's direction setting (`elk.direction: "RIGHT"` for LR, `"DOWN"` for TB).
3. ELK computes: container sizes (fit children), child positions within containers, edge routing around container boundaries.
4. Transform ELK output → React Flow nodes (with `parentId` for nesting, absolute→parent-relative coordinates) and edges.

### Manual position overrides

- When a user drags a node, persist the position delta via the existing `PUT /processes/{id}/nodes` endpoint.
- On next load: run ELK layout first, then apply saved overrides on top.
- "Reset Layout" button clears saved positions and re-runs ELK.

### Performance

- `elkjs` runs in a Web Worker (ships with one). Layout for ~100 nodes is <100ms, ~500 nodes <500ms.
- Layout computed on initial load and on expand/collapse — not on every frame.

## Collapse / Expand

### State management

- Local React state: `Map<string, boolean>` tracking which containers are expanded. Session-level — not persisted to the backend.
- Initialized from the org setting: if `process_map_default_state = "collapsed"`, all top-level containers (direct children of the domain) start collapsed. Their descendants are hidden by inheritance.

### Collapsed behavior

- Children (steps and sub-containers) removed from the React Flow node set.
- Container node shrinks to a compact summary: name label + step count badge (e.g., "Order Entry · 12 steps").
- Edges that connected to hidden children re-target to the collapsed container. Multiple edges to the same external target collapse into a single **dashed edge** with a count badge.

### Expanded behavior

- Re-run ELK layout for the affected subtree (incremental, not full graph).
- Children animate in. Container grows to fit.
- Edges re-attach to specific child nodes.

### Interaction

- Click the container header bar to toggle expand/collapse.
- Toolbar buttons: "Expand All" / "Collapse All".

## Visual Design

### Container node (non-leaf process)

- Rounded rectangle with subtle border and a colored header bar.
- Color derived from depth level: level 1 = navy, level 2 = slate, level 3 = lighter shade. Makes nesting depth obvious at a glance.
- Header: process name, chevron toggle icon, step count badge.
- Expanded: body area is near-white fill holding children with breathing-room padding.
- Collapsed: compact pill — just the header bar, similar visual weight to a step card.
- At extreme depth (5+): innermost containers use dashed borders to reduce visual noise.

### Step card (leaf node)

Existing `ProcessNodeComponent` design carries forward unchanged:
- Card with colored left bar (navy = process, orange = doc, emerald = data).
- Icon, title, subtitle.
- Source and target handles for edges.

### Edges

- **Normal handoffs:** Slate bezier curves, arrow marker, hoverable label pill. Existing design.
- **Gap edges:** Red stroke, red pill with warning icon. Existing design.
- **Cross-container edges:** No special treatment — same styling, ELK handles routing around boundaries.
- **Collapsed aggregate edges:** Dashed stroke + count badge on label to distinguish from direct edges.

### Toolbar (top panel)

New additions alongside existing zoom/fit-view controls:
- **Direction toggle:** LR ↔ TB icon button. Applies immediately, persists to org setting.
- **Expand All / Collapse All** buttons.
- **Reset Layout** button (clears manual position overrides, re-runs ELK).
- **Minimap** enabled by default on domain maps for navigation in large graphs.

## Navigation & Routing

### Changes

- Remove "Open process map" link from non-domain processes in the processes list page. Only domain-level rows keep it.
- Header "Process Map" shortcut links to the first domain (not the first flat list item).
- Route stays `/processes/:id/map`. The `id` is always a domain ID.

### Deep-linking non-domain IDs

If someone navigates to `/processes/:id/map` with a non-domain process ID:
- Redirect to that process's parent domain map.
- Auto-expand the container tree down to the requested process.
- Scroll/zoom to center it on the canvas.

### Child process actions

Child processes retain their existing Confirm/Reject buttons on the processes list page. No changes to the review workflow.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Empty domain (no children) | Existing "No graph data yet" empty state with discovery prompt |
| Single-level domain (leaf steps directly under domain) | Flat layout — step cards with edges, no containers. New toolbar still present. |
| Very deep nesting (4+ levels) | ELK handles natively. Depth-shifted colors + dashed borders at 5+ levels. |
| Orphan steps (broken parent chain) | Placed in an "Uncategorized" container at root level, visually flagged. |
| No edges between steps | Valid state — containers and cards render from hierarchy alone. |
| Large domains (100+ leaf steps) | Minimap enabled, fit-to-view on initial load. ELK Web Worker keeps UI responsive. |

## Out of Scope (Flagged for Future Specs)

- **Bulk review actions:** "Accept All" / "Reject All" at the domain level to confirm/reject all discovered children.
- **In-map review:** Confirm/reject steps directly from the domain map canvas (e.g., right-click context menu).
- **Click-to-navigate from list:** Clicking a child process name in the accordion tree navigates to the domain map with that process highlighted. (Possible fast-follow.)

## Dependencies

| Dependency | Purpose | Size |
|------------|---------|------|
| `elkjs` | Hierarchical compound graph layout | ~200KB |

React Flow (`@xyflow/react`) is already installed.

## Open Question

The choice of ELK + React Flow and the visual design conventions described above are **pending validation** against 2026 enterprise BPM tool standards, industry research, and modern process mapping best practices. An industry research pass will be conducted before implementation begins. If research reveals a better approach or conflicting conventions, this spec will be updated accordingly.
