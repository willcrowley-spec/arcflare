from app.services.arcbrain.code_graph import (
    CodebaseMemoryProjectReader,
    code_node_type,
    parse_codegraph_repos,
)


def test_parse_codegraph_repos_accepts_named_and_unnamed_entries():
    repos = parse_codegraph_repos("arcflare=/app; /workspace/customer-portal ")

    assert repos == [
        ("arcflare", "/app"),
        ("customer-portal", "/workspace/customer-portal"),
    ]


def test_codebase_memory_project_reader_normalizes_architecture_and_edges():
    reader = CodebaseMemoryProjectReader(project_alias="arcflare", root_path="/app")

    project = reader.from_cli_payloads(
        index_payload={
            "project": "arcflare",
            "status": "indexed",
            "nodes": 10,
            "edges": 20,
        },
        architecture_payload={
            "total_nodes": 10,
            "total_edges": 20,
            "node_labels": [{"label": "Function", "count": 3}],
            "edge_types": [{"type": "CALLS", "count": 2}],
            "languages": [{"language": "python", "file_count": 4}],
            "routes": [{"method": "GET", "path": "/accounts", "handler": "list_accounts"}],
            "hotspots": [{"name": "AccountService", "qualified_name": "pkg.AccountService", "fan_in": 7}],
        },
        search_payloads={
            "Function": {
                "results": [
                    {
                        "name": "list_accounts",
                        "qualified_name": "pkg.routes.list_accounts",
                        "label": "Function",
                        "file_path": "backend/app/api/routes/accounts.py",
                        "start_line": 10,
                        "end_line": 18,
                        "in_degree": 1,
                        "out_degree": 2,
                    }
                ]
            },
            "Route": {
                "results": [
                    {
                        "name": "/accounts",
                        "qualified_name": "__route__GET__/accounts",
                        "label": "Route",
                        "file_path": "backend/app/api/routes/accounts.py",
                        "in_degree": 1,
                        "out_degree": 0,
                    }
                ]
            },
        },
        edge_payloads={
            "HANDLES": {
                "rows": [
                    [
                        "list_accounts",
                        "pkg.routes.list_accounts",
                        "Function",
                        "backend/app/api/routes/accounts.py",
                        "HANDLES",
                        "/accounts",
                        "__route__GET__/accounts",
                        "Route",
                        "backend/app/api/routes/accounts.py",
                    ]
                ]
            }
        },
    )

    assert project.project_id == "arcflare"
    assert project.metrics["total_nodes"] == 10
    assert {node.kind for node in project.nodes} >= {"Function", "Route", "File"}
    assert any(edge.edge_type == "HANDLES" for edge in project.edges)
    assert code_node_type("Route") == "code_route"
