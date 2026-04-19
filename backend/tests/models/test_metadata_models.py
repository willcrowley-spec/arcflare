import uuid

from app.models.metadata import MetadataDependency


def test_metadata_dependency_instantiation():
    row = MetadataDependency(
        org_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        source_type="flow",
        source_api_name="My_Flow",
        target_type="object",
        target_api_name="Account",
        relationship_type="triggers_on",
        metadata_json={"edge_detail": "test"},
    )
    assert row.source_api_name == "My_Flow"
    assert row.metadata_json["edge_detail"] == "test"
