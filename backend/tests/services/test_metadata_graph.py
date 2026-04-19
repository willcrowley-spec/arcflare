def test_metadata_graph_exports():
    from app.services.metadata_graph import build_dependency_graph, detect_metadata_communities

    assert callable(build_dependency_graph)
    assert callable(detect_metadata_communities)
