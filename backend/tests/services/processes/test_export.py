from uuid import UUID

from app.services.processes.export import render_mermaid


DOMAIN_ID = UUID("00000000-0000-0000-0000-000000000010")
PROCESS_ID = UUID("00000000-0000-0000-0000-000000000020")
STEP_A_ID = UUID("00000000-0000-0000-0000-000000000030")
STEP_B_ID = UUID("00000000-0000-0000-0000-000000000040")


def test_render_mermaid_is_deterministic_and_marks_gaps_and_review_nodes():
    graph = {
        "domain": {"id": str(DOMAIN_ID), "name": "Revenue Operations"},
        "hierarchy": [
            {
                "id": str(PROCESS_ID),
                "name": "Lead Intake",
                "level": "process",
                "needs_review": False,
                "is_leaf": False,
                "children": [
                    {
                        "id": str(STEP_A_ID),
                        "name": "Capture Lead",
                        "level": "step",
                        "needs_review": False,
                        "is_leaf": True,
                        "children": [],
                    },
                    {
                        "id": str(STEP_B_ID),
                        "name": "Qualify Lead",
                        "level": "step",
                        "needs_review": True,
                        "is_leaf": True,
                        "children": [],
                    },
                ],
            }
        ],
        "edges": [
            {
                "id": "handoff-1",
                "source_id": str(STEP_A_ID),
                "target_id": str(STEP_B_ID),
                "label": "manual",
                "is_gap": True,
            }
        ],
    }

    rendered = render_mermaid(graph, direction="LR")

    assert rendered == render_mermaid(graph, direction="LR")
    assert rendered.startswith("flowchart LR")
    assert 'subgraph n_00000000_0000_0000_0000_000000000020["Lead Intake"]' in rendered
    assert 'n_00000000_0000_0000_0000_000000000030["Capture Lead"]' in rendered
    assert 'n_00000000_0000_0000_0000_000000000040["Qualify Lead"]' in rendered
    assert (
        'n_00000000_0000_0000_0000_000000000030 -->|manual| '
        'n_00000000_0000_0000_0000_000000000040'
    ) in rendered
    assert "class n_00000000_0000_0000_0000_000000000040 reviewNode" in rendered
    assert "classDef reviewNode" in rendered
    assert "classDef gapNode" in rendered
    assert "linkStyle 0 stroke:#ef4444" in rendered
