"""Export process graphs to external formats."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
