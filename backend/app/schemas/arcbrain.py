from pydantic import BaseModel, Field


class ArcbrainNode(BaseModel):
    id: str
    label: str
    node_type: str
    layer: str
    source_type: str
    source_ref: str
    confidence: float = 0.0
    freshness: str = "current"
    risk_level: str = "unknown"
    replaceability_score: float = 0.0
    economic_value: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    metrics_json: dict = Field(default_factory=dict)
    metadata_json: dict = Field(default_factory=dict)
    summary: str | None = None
    community_id: str | None = None


class ArcbrainEdge(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    weight: float = 1.0
    confidence: float = 0.0
    evidence_refs: list[str] = Field(default_factory=list)
    metrics_json: dict = Field(default_factory=dict)
    metadata_json: dict = Field(default_factory=dict)


class ArcbrainCommunity(BaseModel):
    id: str
    label: str
    layer: str = "evidence"
    source_type: str = "community"
    source_ref: str
    summary: str | None = None
    confidence: float = 0.0
    member_node_ids: list[str] = Field(default_factory=list)
    metrics_json: dict = Field(default_factory=dict)
    metadata_json: dict = Field(default_factory=dict)


class ArcbrainSnapshotResponse(BaseModel):
    snapshot_id: str
    graph_version: str = "arcbrain-v0"
    nodes: list[ArcbrainNode] = Field(default_factory=list)
    edges: list[ArcbrainEdge] = Field(default_factory=list)
    communities: list[ArcbrainCommunity] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)


class ArcbrainSearchResponse(BaseModel):
    query: str
    nodes: list[ArcbrainNode] = Field(default_factory=list)
    edges: list[ArcbrainEdge] = Field(default_factory=list)
    total_matches: int = 0
    summary: dict = Field(default_factory=dict)


class ArcbrainBlastRadiusResponse(BaseModel):
    focus_node: ArcbrainNode
    upstream_nodes: list[ArcbrainNode] = Field(default_factory=list)
    downstream_nodes: list[ArcbrainNode] = Field(default_factory=list)
    related_nodes: list[ArcbrainNode] = Field(default_factory=list)
    edges: list[ArcbrainEdge] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)


class ArcbrainReplacementHeatResponse(BaseModel):
    nodes: list[ArcbrainNode] = Field(default_factory=list)
    edges: list[ArcbrainEdge] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
