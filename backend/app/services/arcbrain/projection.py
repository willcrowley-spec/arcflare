from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.schemas.arcbrain import (
    ArcbrainBlastRadiusResponse,
    ArcbrainCommunity,
    ArcbrainEdge,
    ArcbrainNode,
    ArcbrainReplacementHeatResponse,
    ArcbrainSearchResponse,
    ArcbrainSnapshotResponse,
)


@dataclass
class ArcbrainSourceData:
    metadata_objects: list[MetadataObject] = field(default_factory=list)
    metadata_fields: list[MetadataField] = field(default_factory=list)
    metadata_automations: list[MetadataAutomation] = field(default_factory=list)
    metadata_components: list[MetadataComponent] = field(default_factory=list)
    metadata_dependencies: list[MetadataDependency] = field(default_factory=list)
    business_processes: list[BusinessProcess] = field(default_factory=list)
    process_handoffs: list[ProcessHandoff] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    communities: list[Community] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)


class ArcbrainProjectionService:
    graph_version = "arcbrain-v0"

    async def snapshot(self, org_id: UUID, db: AsyncSession) -> ArcbrainSnapshotResponse:
        data = await self.load_source_data(org_id, db)
        return self.project(org_id, data)

    async def load_source_data(self, org_id: UUID, db: AsyncSession) -> ArcbrainSourceData:
        metadata_objects = (
            (
                await db.execute(
                    select(MetadataObject)
                    .where(MetadataObject.org_id == org_id)
                    .order_by(MetadataObject.api_name)
                )
            )
            .scalars()
            .all()
        )
        metadata_fields = (
            (
                await db.execute(
                    select(MetadataField)
                    .join(MetadataObject, MetadataField.object_id == MetadataObject.id)
                    .where(MetadataObject.org_id == org_id)
                    .order_by(MetadataObject.api_name, MetadataField.api_name)
                )
            )
            .scalars()
            .all()
        )
        metadata_automations = (
            (
                await db.execute(
                    select(MetadataAutomation)
                    .where(MetadataAutomation.org_id == org_id)
                    .order_by(MetadataAutomation.automation_type, MetadataAutomation.api_name)
                )
            )
            .scalars()
            .all()
        )
        metadata_components = (
            (
                await db.execute(
                    select(MetadataComponent)
                    .where(MetadataComponent.org_id == org_id)
                    .order_by(MetadataComponent.component_category, MetadataComponent.api_name)
                )
            )
            .scalars()
            .all()
        )
        metadata_dependencies = (
            (
                await db.execute(
                    select(MetadataDependency)
                    .where(MetadataDependency.org_id == org_id)
                    .order_by(
                        MetadataDependency.source_type,
                        MetadataDependency.source_api_name,
                        MetadataDependency.target_type,
                        MetadataDependency.target_api_name,
                    )
                )
            )
            .scalars()
            .all()
        )
        business_processes = (
            (
                await db.execute(
                    select(BusinessProcess)
                    .where(BusinessProcess.org_id == org_id)
                    .order_by(BusinessProcess.level, BusinessProcess.name)
                )
            )
            .scalars()
            .all()
        )
        process_handoffs = (
            (
                await db.execute(
                    select(ProcessHandoff)
                    .where(ProcessHandoff.org_id == org_id)
                    .order_by(ProcessHandoff.source_process_id, ProcessHandoff.target_process_id)
                )
            )
            .scalars()
            .all()
        )
        concepts = (
            (
                await db.execute(
                    select(Concept).where(Concept.org_id == org_id).order_by(Concept.name)
                )
            )
            .scalars()
            .all()
        )
        communities = (
            (
                await db.execute(
                    select(Community).where(Community.org_id == org_id).order_by(Community.label)
                )
            )
            .scalars()
            .all()
        )
        recommendations = (
            (
                await db.execute(
                    select(Recommendation)
                    .where(Recommendation.org_id == org_id)
                    .order_by(Recommendation.category, Recommendation.title)
                )
            )
            .scalars()
            .all()
        )

        return ArcbrainSourceData(
            metadata_objects=list(metadata_objects),
            metadata_fields=list(metadata_fields),
            metadata_automations=list(metadata_automations),
            metadata_components=list(metadata_components),
            metadata_dependencies=list(metadata_dependencies),
            business_processes=list(business_processes),
            process_handoffs=list(process_handoffs),
            concepts=list(concepts),
            communities=list(communities),
            recommendations=list(recommendations),
        )

    def project(self, org_id: UUID, data: ArcbrainSourceData) -> ArcbrainSnapshotResponse:
        nodes: dict[str, ArcbrainNode] = {}
        edges: dict[str, ArcbrainEdge] = {}
        communities: dict[str, ArcbrainCommunity] = {}
        object_by_id: dict[str, MetadataObject] = {}
        object_node_by_api: dict[str, str] = {}
        automation_node_by_type_api: dict[tuple[str, str], str] = {}
        component_node_by_type_api: dict[tuple[str, str], str] = {}
        process_node_by_id: dict[str, str] = {}
        concept_node_by_id: dict[str, str] = {}

        def add_node(node: ArcbrainNode) -> None:
            nodes.setdefault(node.id, node)

        def add_edge(edge: ArcbrainEdge) -> None:
            if edge.source_node_id in nodes and edge.target_node_id in nodes:
                edges.setdefault(edge.id, edge)

        for obj in sorted(data.metadata_objects, key=lambda row: row.api_name):
            object_by_id[str(obj.id)] = obj
            node_id = _node_id("metadata_object", obj.id)
            object_node_by_api[_norm(obj.api_name)] = node_id
            add_node(
                ArcbrainNode(
                    id=node_id,
                    label=obj.label or obj.api_name,
                    node_type="metadata_object",
                    layer="metadata",
                    source_type="metadata_object",
                    source_ref=str(obj.id),
                    confidence=_clamp(float(obj.velocity_score or 0.0)),
                    freshness="current",
                    risk_level=_object_risk(obj),
                    replaceability_score=0.2 if obj.record_count else 0.1,
                    economic_value=float(obj.record_count or 0),
                    evidence_refs=[f"metadata_object:{obj.api_name}"],
                    metrics_json={
                        "field_count": int(obj.field_count or 0),
                        "record_count": int(obj.record_count or 0),
                        "velocity_score": float(obj.velocity_score or 0.0),
                    },
                    metadata_json={
                        **_as_dict(obj.metadata_json),
                        "api_name": obj.api_name,
                        "classification": obj.classification,
                        "object_type": obj.object_type,
                        "is_custom": bool(obj.is_custom),
                    },
                    summary=f"{obj.api_name} object with {int(obj.record_count or 0)} records.",
                )
            )

        for field_row in sorted(data.metadata_fields, key=lambda row: row.api_name):
            obj = object_by_id.get(str(field_row.object_id))
            parent_id = _node_id("metadata_object", field_row.object_id)
            field_node_id = _node_id("metadata_field", field_row.id)
            add_node(
                ArcbrainNode(
                    id=field_node_id,
                    label=field_row.label or field_row.api_name,
                    node_type="metadata_field",
                    layer="metadata",
                    source_type="metadata_field",
                    source_ref=str(field_row.id),
                    confidence=0.7,
                    freshness="current",
                    risk_level="medium" if field_row.is_required else "low",
                    replaceability_score=0.1,
                    economic_value=0.0,
                    evidence_refs=[f"metadata_field:{field_row.api_name}"],
                    metrics_json={
                        "is_required": bool(field_row.is_required),
                        "is_indexed": bool(field_row.is_indexed),
                        "is_unique": bool(field_row.is_unique),
                    },
                    metadata_json={
                        **_as_dict(field_row.metadata_json),
                        "api_name": field_row.api_name,
                        "object_api_name": obj.api_name if obj else None,
                        "field_type": field_row.field_type,
                    },
                    summary=f"{field_row.field_type or 'Field'} on {obj.api_name if obj else 'object'}.",
                )
            )
            add_edge(
                _edge(
                    "part_of",
                    field_node_id,
                    parent_id,
                    confidence=0.9,
                    evidence_refs=[f"metadata_field:{field_row.api_name}"],
                )
            )

        for automation in sorted(
            data.metadata_automations, key=lambda row: (row.automation_type, row.api_name)
        ):
            node_id = _node_id("automation", automation.id)
            automation_node_by_type_api[(_norm(automation.automation_type), _norm(automation.api_name))] = node_id
            add_node(
                ArcbrainNode(
                    id=node_id,
                    label=automation.label or automation.api_name,
                    node_type="automation",
                    layer="metadata",
                    source_type="automation",
                    source_ref=str(automation.id),
                    confidence=_automation_confidence(automation),
                    freshness="current",
                    risk_level=_complexity_risk(automation.complexity_score),
                    replaceability_score=_automation_replaceability(automation),
                    economic_value=0.0,
                    evidence_refs=[f"automation:{automation.api_name}"],
                    metrics_json={
                        "complexity_score": automation.complexity_score,
                        "status": automation.status,
                    },
                    metadata_json={
                        **_as_dict(automation.metadata_json),
                        "api_name": automation.api_name,
                        "automation_type": automation.automation_type,
                        "related_object": automation.related_object,
                    },
                    summary=f"{automation.automation_type} automation for {automation.related_object or 'Salesforce'}.",
                )
            )
            target_id = object_node_by_api.get(_norm(automation.related_object))
            if target_id:
                add_edge(
                    _edge(
                        "triggers",
                        node_id,
                        target_id,
                        confidence=0.8,
                        evidence_refs=[f"automation:{automation.api_name}"],
                    )
                )

        for component in sorted(
            data.metadata_components, key=lambda row: (row.component_category, row.api_name)
        ):
            node_id = _node_id("metadata_component", component.id)
            node_type = _component_node_type(component.component_category)
            component_node_by_type_api[(node_type, _norm(component.api_name))] = node_id
            component_node_by_type_api[(_norm(component.component_category), _norm(component.api_name))] = node_id
            add_node(
                ArcbrainNode(
                    id=node_id,
                    label=component.label or component.api_name,
                    node_type=node_type,
                    layer="metadata",
                    source_type="metadata_component",
                    source_ref=str(component.id),
                    confidence=0.75,
                    freshness="current",
                    risk_level="medium" if component.status == "Active" else "low",
                    replaceability_score=0.15,
                    economic_value=0.0,
                    evidence_refs=[f"component:{component.api_name}"],
                    metrics_json={"status": component.status},
                    metadata_json={
                        **_as_dict(component.metadata_json),
                        "api_name": component.api_name,
                        "component_category": component.component_category,
                        "related_object": component.related_object,
                    },
                    summary=f"{component.component_category} component.",
                )
            )
            target_id = object_node_by_api.get(_norm(component.related_object))
            if target_id:
                add_edge(
                    _edge(
                        "depends_on",
                        node_id,
                        target_id,
                        confidence=0.75,
                        evidence_refs=[f"component:{component.api_name}"],
                    )
                )

        for process in sorted(data.business_processes, key=lambda row: (row.level, row.name)):
            node_id = _node_id("business_process", process.id)
            process_node_by_id[str(process.id)] = node_id
            category = process.category or process.level or "process"
            add_node(
                ArcbrainNode(
                    id=node_id,
                    label=process.name,
                    node_type="business_process",
                    layer="process",
                    source_type="business_process",
                    source_ref=str(process.id),
                    confidence=_clamp(float(process.confidence_score or 0.6)),
                    freshness="current",
                    risk_level="high" if process.needs_review else _process_risk(process),
                    replaceability_score=_potential_score(process.automation_potential),
                    economic_value=float(process.managed_asset_count or 0),
                    evidence_refs=_string_list(process.evidence_sources) or [f"process:{process.name}"],
                    metrics_json={
                        "managed_asset_count": int(process.managed_asset_count or 0),
                        "sub_process_count": int(process.sub_process_count or 0),
                        "needs_review": bool(process.needs_review),
                    },
                    metadata_json={
                        **_as_dict(process.metadata_json),
                        "category": category,
                        "level": process.level,
                        "status": process.status,
                        "automation_potential": process.automation_potential,
                        "value_classification": process.value_classification,
                        "complexity_score": process.complexity_score,
                        "actors": process.actors or [],
                        "system_touchpoints": process.system_touchpoints or [],
                    },
                    summary=process.description or process.narrative,
                )
            )
            if process.parent_id:
                add_edge(
                    _edge(
                        "part_of",
                        node_id,
                        _node_id("business_process", process.parent_id),
                        confidence=_clamp(float(process.confidence_score or 0.6)),
                        evidence_refs=[f"process:{process.name}"],
                    )
                )

        for concept in sorted(data.concepts, key=lambda row: row.name):
            node_id = _node_id("concept", concept.id)
            concept_node_by_id[str(concept.id)] = node_id
            add_node(
                ArcbrainNode(
                    id=node_id,
                    label=concept.display_name or concept.name,
                    node_type="evidence_claim",
                    layer="evidence",
                    source_type="concept",
                    source_ref=str(concept.id),
                    confidence=_clamp(min(0.9, 0.45 + (concept.frequency or 0) / 20)),
                    freshness="current",
                    risk_level="low",
                    replaceability_score=0.0,
                    economic_value=0.0,
                    evidence_refs=[f"concept:{concept.name}"],
                    metrics_json={"frequency": int(concept.frequency or 0)},
                    metadata_json={"concept_type": concept.concept_type, "name": concept.name},
                    summary=f"{concept.concept_type} concept from evidence.",
                )
            )

        for community in sorted(data.communities, key=lambda row: row.label or ""):
            community_id = _node_id("community", community.id)
            member_node_ids = [
                concept_node_by_id[concept_id]
                for concept_id in _string_list(community.member_concept_ids)
                if concept_id in concept_node_by_id
            ]
            communities[community_id] = ArcbrainCommunity(
                id=community_id,
                label=community.label or "Community",
                layer="evidence",
                source_ref=str(community.id),
                summary=community.summary,
                confidence=0.65,
                member_node_ids=member_node_ids,
                metrics_json={"level": community.level, "member_count": len(member_node_ids)},
                metadata_json={**_as_dict(community.metadata_json), "source": community.source},
            )
            add_node(
                ArcbrainNode(
                    id=community_id,
                    label=community.label or "Community",
                    node_type="business_domain",
                    layer="evidence",
                    source_type="community",
                    source_ref=str(community.id),
                    confidence=0.65,
                    freshness="current",
                    risk_level="low",
                    replaceability_score=0.0,
                    economic_value=0.0,
                    evidence_refs=[f"community:{community.label or community.id}"],
                    metrics_json={"level": community.level, "member_count": len(member_node_ids)},
                    metadata_json={**_as_dict(community.metadata_json), "source": community.source},
                    summary=community.summary,
                )
            )
            for member_id in member_node_ids:
                add_edge(
                    _edge(
                        "part_of",
                        member_id,
                        community_id,
                        confidence=0.65,
                        evidence_refs=[f"community:{community.label or community.id}"],
                    )
                )

        for recommendation in sorted(data.recommendations, key=lambda row: row.title):
            node_id = _node_id("recommendation", recommendation.id)
            category = recommendation.category or "uncategorized"
            economic_value = _recommendation_value(recommendation)
            arc_score = _as_dict(recommendation.arc_score_json)
            add_node(
                ArcbrainNode(
                    id=node_id,
                    label=recommendation.title,
                    node_type="recommendation",
                    layer="replacement",
                    source_type="recommendation",
                    source_ref=str(recommendation.id),
                    confidence=_recommendation_confidence(recommendation),
                    freshness="current",
                    risk_level=_recommendation_risk(recommendation),
                    replaceability_score=_clamp(float(arc_score.get("score") or recommendation.composite_score or 0.0)),
                    economic_value=economic_value,
                    evidence_refs=[f"recommendation:{recommendation.id}"],
                    metrics_json={
                        "estimated_roi": economic_value,
                        "composite_score": recommendation.composite_score,
                        "priority": recommendation.priority,
                    },
                    metadata_json={
                        "category": category,
                        "status": recommendation.status,
                        "recommendation_type": recommendation.recommendation_type,
                        "automation_type": recommendation.automation_type,
                        "arc_score": arc_score,
                        "financial_evaluation_status": recommendation.financial_evaluation_status,
                    },
                    summary=recommendation.description,
                )
            )
            for process_id in _string_list(recommendation.linked_process_ids):
                target_id = process_node_by_id.get(process_id)
                if target_id:
                    add_edge(
                        _edge(
                            "replaces",
                            node_id,
                            target_id,
                            confidence=_recommendation_confidence(recommendation),
                            evidence_refs=[f"recommendation:{recommendation.id}"],
                            metrics_json={"economic_value": economic_value},
                        )
                    )
            if recommendation.domain_id:
                target_id = process_node_by_id.get(str(recommendation.domain_id))
                if target_id:
                    add_edge(
                        _edge(
                            "part_of",
                            node_id,
                            target_id,
                            confidence=_recommendation_confidence(recommendation),
                            evidence_refs=[f"recommendation:{recommendation.id}"],
                        )
                    )

        for dependency in sorted(
            data.metadata_dependencies,
            key=lambda row: (
                row.source_type,
                row.source_api_name,
                row.target_type,
                row.target_api_name,
                row.relationship_type,
            ),
        ):
            source_id = _resolve_metadata_ref(
                dependency.source_type,
                dependency.source_api_name,
                object_node_by_api,
                automation_node_by_type_api,
                component_node_by_type_api,
            )
            target_id = _resolve_metadata_ref(
                dependency.target_type,
                dependency.target_api_name,
                object_node_by_api,
                automation_node_by_type_api,
                component_node_by_type_api,
            )
            if source_id and target_id:
                add_edge(
                    _edge(
                        _edge_type(dependency.relationship_type),
                        source_id,
                        target_id,
                        confidence=0.8,
                        evidence_refs=[f"metadata_dependency:{dependency.id}"],
                        metadata_json=_as_dict(dependency.metadata_json),
                    )
                )

        for handoff in sorted(
            data.process_handoffs,
            key=lambda row: (str(row.source_process_id), str(row.target_process_id)),
        ):
            source_id = process_node_by_id.get(str(handoff.source_process_id))
            target_id = process_node_by_id.get(str(handoff.target_process_id))
            if source_id and target_id:
                add_edge(
                    _edge(
                        "hands_off_to",
                        source_id,
                        target_id,
                        weight=1.3 if handoff.is_gap else 1.0,
                        confidence=_clamp(float(handoff.confidence_score or 0.0)),
                        evidence_refs=_string_list(handoff.evidence_sources)
                        or [f"handoff:{handoff.id}"],
                        metrics_json={
                            "is_gap": bool(handoff.is_gap),
                            "needs_review": bool(handoff.needs_review),
                        },
                        metadata_json={
                            **_as_dict(handoff.metadata_json),
                            "handoff_type": handoff.handoff_type,
                            "gap_status": handoff.gap_status,
                            "description": handoff.description,
                        },
                    )
                )

        ordered_nodes = sorted(nodes.values(), key=lambda node: node.id)
        ordered_edges = sorted(edges.values(), key=lambda edge: edge.id)
        ordered_communities = sorted(communities.values(), key=lambda community: community.id)

        return ArcbrainSnapshotResponse(
            snapshot_id=f"arcbrain:{org_id}:v0",
            graph_version=self.graph_version,
            nodes=ordered_nodes,
            edges=ordered_edges,
            communities=ordered_communities,
            summary=_summary(ordered_nodes, ordered_edges),
        )

    def search(
        self, snapshot: ArcbrainSnapshotResponse, query: str, limit: int = 25
    ) -> ArcbrainSearchResponse:
        normalized = query.strip().lower()
        if not normalized:
            return ArcbrainSearchResponse(query=query, nodes=[], edges=[], total_matches=0, summary={})

        matches = [
            node
            for node in snapshot.nodes
            if normalized in " ".join(
                [
                    node.label,
                    node.node_type,
                    node.source_type,
                    node.summary or "",
                    str(node.metadata_json.get("category", "")),
                    str(node.metadata_json.get("api_name", "")),
                ]
            ).lower()
        ]
        matches = sorted(matches, key=lambda node: (-node.confidence, node.label.lower(), node.id))[:limit]
        matched_ids = {node.id for node in matches}
        incident_edges = [
            edge
            for edge in snapshot.edges
            if edge.source_node_id in matched_ids or edge.target_node_id in matched_ids
        ]
        return ArcbrainSearchResponse(
            query=query,
            nodes=matches,
            edges=incident_edges,
            total_matches=len(matches),
            summary={"edge_count": len(incident_edges)},
        )

    def get_node(self, snapshot: ArcbrainSnapshotResponse, node_id: str) -> ArcbrainNode | None:
        return next((node for node in snapshot.nodes if node.id == node_id), None)

    def blast_radius(
        self, snapshot: ArcbrainSnapshotResponse, node_id: str, depth: int = 1
    ) -> ArcbrainBlastRadiusResponse:
        focus = self.get_node(snapshot, node_id)
        if focus is None:
            raise ValueError("Node not found")
        depth = max(1, min(depth, 4))
        node_by_id = {node.id: node for node in snapshot.nodes}

        upstream_ids = _walk(snapshot.edges, {node_id}, depth, incoming=True)
        downstream_ids = _walk(snapshot.edges, {node_id}, depth, incoming=False)
        related_ids = upstream_ids | downstream_ids
        incident_edges = [
            edge
            for edge in snapshot.edges
            if edge.source_node_id in related_ids | {node_id}
            and edge.target_node_id in related_ids | {node_id}
        ]
        related_nodes = sorted(
            [node_by_id[node_id] for node_id in related_ids if node_id in node_by_id],
            key=lambda node: node.id,
        )
        scoped_nodes = [focus, *related_nodes]

        return ArcbrainBlastRadiusResponse(
            focus_node=focus,
            upstream_nodes=sorted(
                [node_by_id[node_id] for node_id in upstream_ids if node_id in node_by_id],
                key=lambda node: node.id,
            ),
            downstream_nodes=sorted(
                [node_by_id[node_id] for node_id in downstream_ids if node_id in node_by_id],
                key=lambda node: node.id,
            ),
            related_nodes=related_nodes,
            edges=incident_edges,
            summary={
                "node_count": len(scoped_nodes),
                "edge_count": len(incident_edges),
                "risk_score": round(sum(_risk_weight(node.risk_level) for node in scoped_nodes), 3),
                "economic_value": round(sum(node.economic_value for node in scoped_nodes), 2),
                "average_confidence": _average_confidence(scoped_nodes),
            },
        )

    def replacement_heat(
        self, snapshot: ArcbrainSnapshotResponse
    ) -> ArcbrainReplacementHeatResponse:
        groups: dict[str, dict[str, list[ArcbrainNode]]] = {}
        for node in snapshot.nodes:
            if node.node_type not in {"recommendation", "business_process"}:
                continue
            category = str(node.metadata_json.get("category") or "uncategorized")
            bucket = groups.setdefault(category, {"recommendations": [], "processes": []})
            if node.node_type == "recommendation":
                bucket["recommendations"].append(node)
            else:
                bucket["processes"].append(node)

        heat_nodes: list[ArcbrainNode] = []
        heat_edges: list[ArcbrainEdge] = []
        for category, bucket in sorted(groups.items()):
            members = bucket["recommendations"] + bucket["processes"]
            if not members:
                continue
            recommendation_value = sum(node.economic_value for node in bucket["recommendations"])
            replaceability = mean([node.replaceability_score for node in members]) if members else 0.0
            heat_id = f"replacement_heat:{_slug(category)}"
            heat_node = ArcbrainNode(
                id=heat_id,
                label=category,
                node_type="replacement_heat",
                layer="replacement",
                source_type="replacement_heat",
                source_ref=category,
                confidence=_average_confidence(members),
                freshness="current",
                risk_level=_highest_risk(members),
                replaceability_score=round(_clamp(replaceability), 3),
                economic_value=round(recommendation_value, 2),
                evidence_refs=[ref for node in members for ref in node.evidence_refs][:20],
                metrics_json={
                    "recommendation_count": len(bucket["recommendations"]),
                    "process_count": len(bucket["processes"]),
                    "member_count": len(members),
                },
                metadata_json={"category": category},
                summary=f"{category} replacement heat group.",
            )
            heat_nodes.append(heat_node)
            for member in members:
                heat_edges.append(
                    _edge(
                        "part_of",
                        member.id,
                        heat_id,
                        confidence=member.confidence,
                        evidence_refs=member.evidence_refs,
                    )
                )

        return ArcbrainReplacementHeatResponse(
            nodes=heat_nodes,
            edges=heat_edges,
            summary={
                "heat_node_count": len(heat_nodes),
                "replacement_value_total": round(sum(node.economic_value for node in heat_nodes), 2),
                "average_replaceability": round(
                    mean([node.replaceability_score for node in heat_nodes]), 3
                )
                if heat_nodes
                else 0.0,
            },
        )


def _node_id(source_type: str, source_ref: object) -> str:
    return f"{source_type}:{source_ref}"


def _edge(
    edge_type: str,
    source_node_id: str,
    target_node_id: str,
    *,
    weight: float = 1.0,
    confidence: float = 0.0,
    evidence_refs: list[str] | None = None,
    metrics_json: dict | None = None,
    metadata_json: dict | None = None,
) -> ArcbrainEdge:
    return ArcbrainEdge(
        id=f"{edge_type}:{source_node_id}->{target_node_id}",
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        edge_type=edge_type,
        weight=weight,
        confidence=_clamp(confidence),
        evidence_refs=evidence_refs or [],
        metrics_json=metrics_json or {},
        metadata_json=metadata_json or {},
    )


def _summary(nodes: list[ArcbrainNode], edges: list[ArcbrainEdge]) -> dict:
    counts_by_layer: dict[str, int] = {}
    counts_by_type: dict[str, int] = {}
    for node in nodes:
        counts_by_layer[node.layer] = counts_by_layer.get(node.layer, 0) + 1
        counts_by_type[node.node_type] = counts_by_type.get(node.node_type, 0) + 1
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "counts_by_layer": counts_by_layer,
        "counts_by_type": counts_by_type,
        "replacement_value_total": round(
            sum(node.economic_value for node in nodes if node.layer == "replacement"), 2
        ),
        "average_confidence": _average_confidence(nodes),
        "staleness_status": "stale"
        if any(node.freshness == "stale" for node in nodes)
        else "current",
    }


def _average_confidence(nodes: list[ArcbrainNode]) -> float:
    return round(mean([node.confidence for node in nodes]), 3) if nodes else 0.0


def _as_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _norm(value: object) -> str:
    return str(value or "").strip().lower()


def _slug(value: str) -> str:
    return "-".join(value.strip().lower().replace("_", " ").split()) or "uncategorized"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(float(value), 3)))


def _object_risk(obj: MetadataObject) -> str:
    if obj.classification in {"deprecated", "unused"}:
        return "high"
    if obj.record_count and obj.record_count > 0:
        return "medium"
    return "low"


def _complexity_risk(score: int | None) -> str:
    if score is None:
        return "medium"
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _automation_confidence(automation: MetadataAutomation) -> float:
    base = 0.85 if _norm(automation.status) == "active" else 0.65
    if automation.complexity_score and automation.complexity_score >= 4:
        base -= 0.1
    return _clamp(base)


def _automation_replaceability(automation: MetadataAutomation) -> float:
    if _norm(automation.status) != "active":
        return 0.2
    if automation.complexity_score is None:
        return 0.4
    return _clamp(0.75 - (automation.complexity_score * 0.1))


def _component_node_type(category: str) -> str:
    normalized = _norm(category)
    if normalized in {"apex", "apex_class", "class"}:
        return "apex_class"
    if normalized in {"permission", "permission_set", "profile"}:
        return "permission"
    if normalized in {"package", "managed_package"}:
        return "package"
    if normalized in {"integration", "external_system"}:
        return "integration"
    return normalized or "metadata_component"


def _process_risk(process: BusinessProcess) -> str:
    if _norm(process.complexity_score) == "high":
        return "high"
    if _norm(process.complexity_score) == "low":
        return "low"
    return "medium"


def _potential_score(value: str | None) -> float:
    return {"high": 0.8, "medium": 0.5, "low": 0.2}.get(_norm(value), 0.35)


def _recommendation_value(recommendation: Recommendation) -> float:
    if recommendation.estimated_roi is not None:
        value = recommendation.estimated_roi
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    scenarios = _as_dict(recommendation.scenarios_json)
    npv = _as_dict(scenarios.get("npv"))
    expected = npv.get("expected")
    return float(expected or 0.0)


def _recommendation_confidence(recommendation: Recommendation) -> float:
    opportunity = _as_dict(recommendation.agent_opportunity_json)
    if opportunity.get("confidence") is not None:
        return _clamp(float(opportunity["confidence"]))
    if recommendation.composite_score is not None:
        return _clamp(float(recommendation.composite_score))
    return 0.6


def _recommendation_risk(recommendation: Recommendation) -> str:
    decision = _norm(_as_dict(recommendation.arc_score_json).get("decision"))
    if decision == "ready":
        return "low"
    if decision in {"blocked", "defer"}:
        return "high"
    if recommendation.priority == "high":
        return "medium"
    return "medium"


def _edge_type(value: str) -> str:
    normalized = _norm(value).replace(" ", "_")
    aliases = {
        "triggers_on": "triggers",
        "calls_subflow": "calls",
        "invokes_apex": "calls",
        "sends_email": "uses_system",
    }
    return aliases.get(normalized, normalized or "depends_on")


def _resolve_metadata_ref(
    source_type: str,
    api_name: str,
    object_node_by_api: dict[str, str],
    automation_node_by_type_api: dict[tuple[str, str], str],
    component_node_by_type_api: dict[tuple[str, str], str],
) -> str | None:
    normalized_type = _norm(source_type)
    normalized_api = _norm(api_name)
    if normalized_type in {"object", "metadata_object", "customobject"}:
        return object_node_by_api.get(normalized_api)
    if normalized_type in {"flow", "workflow", "process_builder", "approval_process", "automation"}:
        return automation_node_by_type_api.get((normalized_type, normalized_api)) or next(
            (
                node_id
                for (automation_type, candidate_api), node_id in automation_node_by_type_api.items()
                if candidate_api == normalized_api
            ),
            None,
        )
    component_type = _component_node_type(normalized_type)
    return component_node_by_type_api.get((component_type, normalized_api)) or component_node_by_type_api.get(
        (normalized_type, normalized_api)
    )


def _walk(
    edges: list[ArcbrainEdge], start_ids: set[str], depth: int, *, incoming: bool
) -> set[str]:
    seen: set[str] = set()
    frontier = set(start_ids)
    for _ in range(depth):
        next_frontier: set[str] = set()
        for edge in edges:
            if incoming and edge.target_node_id in frontier and edge.source_node_id not in start_ids:
                next_frontier.add(edge.source_node_id)
            elif not incoming and edge.source_node_id in frontier and edge.target_node_id not in start_ids:
                next_frontier.add(edge.target_node_id)
        next_frontier -= seen
        seen |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    return seen


def _risk_weight(risk_level: str) -> float:
    return {"high": 1.0, "medium": 0.55, "low": 0.2}.get(_norm(risk_level), 0.35)


def _highest_risk(nodes: list[ArcbrainNode]) -> str:
    if any(node.risk_level == "high" for node in nodes):
        return "high"
    if any(node.risk_level == "medium" for node in nodes):
        return "medium"
    if any(node.risk_level == "low" for node in nodes):
        return "low"
    return "unknown"
