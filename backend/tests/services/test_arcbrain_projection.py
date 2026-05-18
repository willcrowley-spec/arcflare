from decimal import Decimal
from uuid import uuid4

from app.models.discovery import ProcessHandoff
from app.models.knowledge import Community, Concept
from app.models.metadata import (
    MetadataAutomation,
    MetadataComponent,
    MetadataDependency,
    MetadataField,
    MetadataObject,
)
from app.models.process import BusinessProcess
from app.models.recommendation import Recommendation
from app.services.arcbrain.projection import ArcbrainProjectionService, ArcbrainSourceData


def _row_id(index: int):
    return uuid4()


def _source_data():
    org_id = uuid4()
    connection_id = uuid4()
    account_id = _row_id(1)
    case_id = _row_id(2)
    field_id = _row_id(3)
    flow_id = _row_id(4)
    component_id = _row_id(5)
    process_id = _row_id(6)
    child_process_id = _row_id(7)
    handoff_id = _row_id(8)
    rec_id = _row_id(9)
    concept_id = _row_id(10)
    community_id = _row_id(11)

    account = MetadataObject(
        id=account_id,
        org_id=org_id,
        connection_id=connection_id,
        api_name="Account",
        label="Account",
        object_type="standard",
        field_count=1,
        record_count=1200,
        is_custom=False,
        managed_package_namespace=None,
        classification="core",
        classification_source="auto",
        velocity_score=0.8,
        metadata_json={"owner": "sales_ops"},
    )
    case = MetadataObject(
        id=case_id,
        org_id=org_id,
        connection_id=connection_id,
        api_name="Case",
        label="Case",
        object_type="standard",
        field_count=0,
        record_count=900,
        is_custom=False,
        managed_package_namespace=None,
        classification="core",
        classification_source="auto",
        velocity_score=0.6,
        metadata_json={},
    )
    rating = MetadataField(
        id=field_id,
        object_id=account_id,
        api_name="Rating",
        label="Rating",
        field_type="Picklist",
        is_custom=False,
        is_required=False,
        is_indexed=False,
        is_unique=False,
        relationship_to=None,
        relationship_type=None,
        metadata_json={},
    )
    flow = MetadataAutomation(
        id=flow_id,
        org_id=org_id,
        connection_id=connection_id,
        automation_type="flow",
        api_name="Case_Intake_Flow",
        label="Case Intake Flow",
        status="Active",
        related_object="Case",
        complexity_score=2,
        metadata_json={},
    )
    component = MetadataComponent(
        id=component_id,
        org_id=org_id,
        connection_id=connection_id,
        component_category="apex_class",
        api_name="AccountService",
        label="Account Service",
        status="Active",
        related_object="Account",
        metadata_json={},
    )
    dependency = MetadataDependency(
        id=_row_id(12),
        org_id=org_id,
        connection_id=connection_id,
        source_type="flow",
        source_api_name="Case_Intake_Flow",
        target_type="object",
        target_api_name="Account",
        relationship_type="reads",
        metadata_json={"source": "parser"},
    )
    process = BusinessProcess(
        id=process_id,
        org_id=org_id,
        name="Support Intake",
        category="service",
        description="Classify inbound cases and route exceptions.",
        status="published",
        source="discovery",
        sub_process_count=1,
        managed_asset_count=2,
        metadata_json={},
        parent_id=None,
        level="domain",
        confidence_score=0.72,
        needs_review=False,
        narrative="High-volume intake work",
        actors=["support_agent"],
        artifacts=["case"],
        trigger_conditions=[],
        decision_logic=[],
        system_touchpoints=["Salesforce"],
        success_criteria=[],
        failure_modes=[],
        value_classification="high",
        complexity_score="low",
        automation_potential="high",
        estimated_duration="10m",
        estimated_frequency="daily",
        sequencing={},
        evidence_sources=["doc:runbook"],
    )
    child_process = BusinessProcess(
        id=child_process_id,
        org_id=org_id,
        name="Triage Case",
        category="service",
        description="Score and assign inbound cases.",
        status="published",
        source="discovery",
        sub_process_count=0,
        managed_asset_count=1,
        metadata_json={},
        parent_id=process_id,
        level="process",
        confidence_score=0.68,
        needs_review=True,
        narrative=None,
        actors=[],
        artifacts=[],
        trigger_conditions=[],
        decision_logic=[],
        system_touchpoints=[],
        success_criteria=[],
        failure_modes=[],
        value_classification="medium",
        complexity_score="medium",
        automation_potential="medium",
        estimated_duration=None,
        estimated_frequency=None,
        sequencing={},
        evidence_sources=[],
    )
    handoff = ProcessHandoff(
        id=handoff_id,
        org_id=org_id,
        source_process_id=process_id,
        target_process_id=child_process_id,
        handoff_type="exception_route",
        description="Escalate exceptions to triage.",
        confidence_score=0.64,
        is_gap=True,
        needs_review=True,
        gap_status="open",
        resolution_note=None,
        metadata_json={},
        evidence_sources=["interview:ops"],
    )
    recommendation = Recommendation(
        id=rec_id,
        org_id=org_id,
        title="Automate support intake",
        description="Replace repetitive support case classification.",
        priority="high",
        category="service",
        estimated_roi=Decimal("240000.00"),
        composite_score=0.81,
        status="active",
        analysis_inputs_json=[],
        actions_json=[],
        impact_json={},
        architecture_health_json={},
        linked_process_ids=[str(process_id), str(child_process_id)],
        recommendation_type="agent_opportunity",
        automation_type="hybrid",
        assumptions_json={},
        scenarios_json={"npv": {"expected": 240000}},
        enrichment_log=[],
        agent_opportunity_json={"confidence": 0.76, "complexity_estimate": "low"},
        arc_score_json={"score": 0.81, "decision": "ready", "evidence_gaps": []},
        linked_step_ids=[],
        financial_evaluation_status="completed",
    )
    concept = Concept(
        id=concept_id,
        org_id=org_id,
        name="support intake",
        display_name="Support Intake",
        concept_type="process",
        frequency=4,
    )
    community = Community(
        id=community_id,
        org_id=org_id,
        parent_id=None,
        level=0,
        label="Service Operations",
        source="document",
        member_concept_ids=[str(concept_id)],
        metadata_json={},
        summary="Support operating model concepts",
    )

    data = ArcbrainSourceData(
        metadata_objects=[account, case],
        metadata_fields=[rating],
        metadata_automations=[flow],
        metadata_components=[component],
        metadata_dependencies=[dependency],
        business_processes=[process, child_process],
        process_handoffs=[handoff],
        concepts=[concept],
        communities=[community],
        recommendations=[recommendation],
    )
    return org_id, data


def test_snapshot_projects_org_assets_into_stable_graph_contract():
    org_id, data = _source_data()

    snapshot = ArcbrainProjectionService().project(org_id, data)

    nodes_by_id = {node.id: node for node in snapshot.nodes}
    account_node = next(
        node for node in snapshot.nodes if node.source_type == "metadata_object" and node.label == "Account"
    )
    rec_node = next(node for node in snapshot.nodes if node.source_type == "recommendation")

    assert account_node.id == f"metadata_object:{data.metadata_objects[0].id}"
    assert account_node.layer == "metadata"
    assert account_node.source_ref == str(data.metadata_objects[0].id)
    assert account_node.confidence == 0.8
    assert account_node.freshness == "current"
    assert account_node.risk_level == "medium"
    assert account_node.replaceability_score == 0.2
    assert account_node.economic_value == 1200.0
    assert account_node.evidence_refs == ["metadata_object:Account"]
    assert rec_node.replaceability_score == 0.81
    assert rec_node.economic_value == 240000.0
    assert rec_node.risk_level == "low"

    edge_keys = {
        (edge.source_node_id, edge.target_node_id, edge.edge_type) for edge in snapshot.edges
    }
    assert (
        f"metadata_field:{data.metadata_fields[0].id}",
        account_node.id,
        "part_of",
    ) in edge_keys
    assert (
        f"automation:{data.metadata_automations[0].id}",
        f"metadata_object:{data.metadata_objects[0].id}",
        "reads",
    ) in edge_keys
    assert (
        f"recommendation:{data.recommendations[0].id}",
        f"business_process:{data.business_processes[0].id}",
        "replaces",
    ) in edge_keys

    assert snapshot.summary["node_count"] == len(nodes_by_id)
    assert snapshot.summary["edge_count"] == len(snapshot.edges)
    assert snapshot.summary["counts_by_layer"]["metadata"] >= 5
    assert snapshot.summary["counts_by_type"]["business_process"] == 2
    assert snapshot.summary["replacement_value_total"] == 240000.0
    assert snapshot.summary["staleness_status"] == "current"


def test_search_matches_labels_types_and_summaries_with_incident_edges():
    org_id, data = _source_data()
    service = ArcbrainProjectionService()
    snapshot = service.project(org_id, data)

    result = service.search(snapshot, "case")

    labels = {node.label for node in result.nodes}
    assert {"Case", "Case Intake Flow", "Triage Case"}.issubset(labels)
    matched_ids = {node.id for node in result.nodes}
    assert result.query == "case"
    assert result.total_matches == len(result.nodes)
    assert result.edges
    assert all(
        edge.source_node_id in matched_ids or edge.target_node_id in matched_ids
        for edge in result.edges
    )


def test_search_returns_conversation_focus_for_lens_and_selected_node():
    org_id, data = _source_data()
    service = ArcbrainProjectionService()
    snapshot = service.project(org_id, data)
    focus_id = f"metadata_object:{data.metadata_objects[1].id}"

    result = service.search(
        snapshot,
        "case",
        limit=10,
        lens="blast_radius",
        focus_node_id=focus_id,
    )

    assert result.answer_type == "graph_search"
    assert result.recommended_view == "blast_radius"
    assert result.confidence > 0
    assert "case" in result.answer.lower()
    assert result.paths
    assert any(focus_id in path for path in result.paths)
    assert result.supporting_claims
    assert result.suggested_next_questions
    assert result.summary["focus_node_id"] == focus_id


def test_search_no_matches_returns_answer_and_missing_evidence():
    org_id, data = _source_data()
    service = ArcbrainProjectionService()
    snapshot = service.project(org_id, data)

    result = service.search(snapshot, "not-a-real-process", lens="trust")

    assert result.nodes == []
    assert result.edges == []
    assert result.total_matches == 0
    assert result.answer_type == "no_match"
    assert result.recommended_view == "trust"
    assert result.confidence == 0
    assert "could not find" in result.answer.lower()
    assert result.missing_evidence


def test_blast_radius_partitions_upstream_downstream_and_related_nodes():
    org_id, data = _source_data()
    service = ArcbrainProjectionService()
    snapshot = service.project(org_id, data)
    focus_id = f"metadata_object:{data.metadata_objects[0].id}"

    result = service.blast_radius(snapshot, focus_id, depth=1)

    assert result.focus_node.id == focus_id
    assert {node.node_type for node in result.upstream_nodes} >= {"automation", "metadata_field"}
    assert result.downstream_nodes == []
    assert result.related_nodes
    assert result.summary["risk_score"] > 0
    assert result.summary["economic_value"] >= 1200.0


def test_replacement_heat_groups_recommendations_and_processes_by_domain():
    org_id, data = _source_data()
    service = ArcbrainProjectionService()
    snapshot = service.project(org_id, data)

    heat = service.replacement_heat(snapshot)

    heat_node = next(node for node in heat.nodes if node.node_type == "replacement_heat")
    assert heat_node.label == "service"
    assert heat_node.layer == "replacement"
    assert heat_node.replaceability_score >= 0.7
    assert heat_node.economic_value == 240000.0
    assert heat_node.metrics_json["recommendation_count"] == 1
    assert heat_node.metrics_json["process_count"] == 2
    assert heat.summary["heat_node_count"] == 1
    assert heat.summary["replacement_value_total"] == 240000.0
