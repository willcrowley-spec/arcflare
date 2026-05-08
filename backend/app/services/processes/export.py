"""Export process graphs to external formats."""

import re
from html import escape
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.process import BusinessProcess
from app.services.processes.domain_graph import get_domain_graph
from app.services.processes.graph import build_process_graph


async def export_json(process_id: UUID, db: AsyncSession) -> dict:
    """Export process graph as JSON."""
    return await build_process_graph(process_id, db)


async def export_svg(process_id: UUID, db: AsyncSession) -> str:
    """
    Export a minimal SVG visualization.

    TODO: richer layout (ELK, dagre) and styling.
    """
    data = await build_process_graph(process_id, db)
    width, height = 800, 600
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<text x="10" y="24" font-size="16">{data["process"]["name"]}</text>',
    ]
    for i, node in enumerate(data["nodes"]):
        x = 40 + (i % 4) * 160
        y = 60 + (i // 4) * 100
        label = node.get("label") or node["id"]
        parts.append(
            f'<rect x="{x}" y="{y}" width="120" height="40" fill="#eef" stroke="#334"/>'
            f'<text x="{x+8}" y="{y+24}" font-size="12">{label[:24]}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


async def export_lucidchart(process_id: UUID, db: AsyncSession) -> dict:
    """
    Produce a portable graph document for Lucidchart import.

    TODO: map to official Lucid JSON schema when credentials available.
    """
    data = await build_process_graph(process_id, db)
    return {"format": "lucidchart-placeholder", "graph": data}


async def export_mermaid(process_id: UUID, db: AsyncSession) -> str:
    """Export a process or domain graph as a Mermaid flowchart."""
    process = await db.get(BusinessProcess, process_id)
    if process is not None and process.level == "domain":
        graph = await get_domain_graph(process_id, process.org_id, db)
    else:
        graph = await build_process_graph(process_id, db)
    return render_mermaid(graph)


def render_mermaid(graph: dict, direction: str = "TB") -> str:
    """Render a normalized process/domain graph into Mermaid flowchart syntax."""
    safe_direction = direction if direction in {"TB", "TD", "BT", "RL", "LR"} else "TB"
    lines = [f"flowchart {safe_direction}"]
    review_node_ids: set[str] = set()

    if "hierarchy" in graph:
        for node in graph.get("hierarchy") or []:
            _append_hierarchy_node(lines, node, review_node_ids, indent="  ")
    else:
        for node in graph.get("nodes") or []:
            node_id = _mermaid_id(node.get("id"))
            label = _mermaid_label(node.get("label") or node.get("name") or node.get("id"))
            lines.append(f'  {node_id}["{label}"]')
            metadata = node.get("metadata_json") or {}
            if node.get("needs_review") or metadata.get("needs_review"):
                review_node_ids.add(node_id)

    gap_node_ids: set[str] = set()
    link_styles: list[str] = []
    for index, edge in enumerate(graph.get("edges") or []):
        source_id = _mermaid_id(edge.get("source_id") or edge.get("source"))
        target_id = _mermaid_id(edge.get("target_id") or edge.get("target"))
        if source_id == _mermaid_id(None) or target_id == _mermaid_id(None):
            continue
        label = _mermaid_edge_label(edge.get("label") or edge.get("kind"))
        connector = f"-->|{label}|" if label else "-->"
        lines.append(f"  {source_id} {connector} {target_id}")
        if edge.get("is_gap"):
            gap_node_ids.update({source_id, target_id})
            link_styles.append(f"linkStyle {index} stroke:#ef4444,stroke-width:2px")

    for node_id in sorted(review_node_ids):
        lines.append(f"  class {node_id} reviewNode")
    if gap_node_ids:
        lines.append(f"  class {','.join(sorted(gap_node_ids))} gapNode")
    lines.append("  classDef reviewNode fill:#fff7ed,stroke:#f59e0b,color:#7c2d12")
    lines.append("  classDef gapNode fill:#fef2f2,stroke:#ef4444,color:#7f1d1d")
    lines.extend(f"  {style}" for style in link_styles)
    return "\n".join(lines)


def _append_hierarchy_node(
    lines: list[str],
    node: dict,
    review_node_ids: set[str],
    indent: str,
) -> None:
    node_id = _mermaid_id(node.get("id"))
    label = _mermaid_label(node.get("name") or node.get("label") or node.get("id"))
    children = node.get("children") or []
    if children:
        lines.append(f'{indent}subgraph {node_id}["{label}"]')
        for child in children:
            _append_hierarchy_node(lines, child, review_node_ids, indent=f"{indent}  ")
        lines.append(f"{indent}end")
    else:
        lines.append(f'{indent}{node_id}["{label}"]')
    if node.get("needs_review"):
        review_node_ids.add(node_id)


def _mermaid_id(raw_id) -> str:
    return "n_" + re.sub(r"[^0-9A-Za-z_]", "_", str(raw_id))


def _mermaid_label(raw_label) -> str:
    return escape(str(raw_label or ""), quote=True).replace("|", "/")


def _mermaid_edge_label(raw_label) -> str:
    return _mermaid_label(raw_label).replace("\n", " ")
