/** Platform connection lifecycle */
export type ConnectionStatus = 'CONNECTED' | 'SYNCING' | 'ERROR' | 'DISCONNECTED' | 'PENDING'

/** Record / document analysis state */
export type RecordStatus = 'CLEAN' | 'ANALYZING' | 'CONFLICT' | 'PENDING' | 'ERROR'

/** Process / recommendation health */
export type ProcessHealthStatus = 'OPTIMIZED' | 'NEEDS_ATTENTION' | 'DRAFT' | 'PARTIAL' | 'HIGH' | 'LOW'

/** Recommendation lifecycle */
export type RecommendationLifecycleStatus = 'ACTIVE' | 'IMPLEMENTED' | 'ARCHIVED' | 'DRAFT'

export type RecommendationPriority = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export type AgentRuntimeStatus = 'RUNNING' | 'IDLE' | 'ERROR' | 'DEPLOYING'

export type PlatformType =
  | 'SALESFORCE'
  | 'HUBSPOT'
  | 'NETSUITE'
  | 'MULESOFT'
  | 'CONFLUENCE'
  | 'CUSTOM'

export type EntityType = 'METADATA' | 'DATA_RECORD' | 'BUSINESS_DOC' | 'AUTOMATION' | 'UNKNOWN'

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  /** Present on some list endpoints */
  has_more?: boolean
  /** Backend metadata pagination uses `pages` */
  pages?: number
}

export interface Organization {
  id: string
  name: string
  industry: string
  employee_count: number
  website?: string
  description?: string
  created_at: string
  updated_at: string
}

export interface User {
  id: string
  email: string
  first_name?: string
  last_name?: string
  role: 'ADMIN' | 'ANALYST' | 'VIEWER'
  organization_id: string
  created_at: string
}

export interface PlatformConnection {
  id: string
  org_id?: string
  /** API field from FastAPI (`platform_type` on wire) */
  platform_type?: string
  instance_url?: string | null
  /** Legacy shape; prefer `platform_type` when present */
  platform?: PlatformType
  label?: string
  status: ConnectionStatus | string
  entity_count: number
  last_sync_at?: string | null
  error_message?: string
  created_at: string
  sync_config_json?: Record<string, unknown>
}

export interface MetadataObject {
  id: string
  org_id?: string
  connection_id?: string
  api_name: string
  label: string | null
  object_type?: string | null
  field_count: number
  record_count: number
  is_custom: boolean
  managed_package_namespace?: string | null
  has_triggers: boolean
  has_flows: boolean
  has_validation_rules: boolean
  metadata_json?: Record<string, unknown>
  last_synced_at?: string | null
  /** Optional legacy / client-normalized fields */
  platform?: PlatformType
  type?: EntityType
  status?: RecordStatus
  last_updated_at?: string
  description?: string
}

export interface MetadataField {
  id: string
  object_id: string
  api_name: string
  label: string
  data_type: string
  required: boolean
  unique: boolean
  external_id: boolean
}

export interface MetadataAutomation {
  id: string
  name: string
  type: 'FLOW' | 'PROCESS_BUILDER' | 'WORKFLOW' | 'APEX_TRIGGER' | 'OTHER'
  platform: PlatformType
  status: string
  last_modified_at: string
}

export interface RecordTelemetry {
  id: string
  object_id: string
  recorded_at: string
  metric: string
  value: number
  unit?: string
}

export interface DocumentChunk {
  id: string
  document_id: string
  content: string
  embedding_id?: string
  page?: number
  created_at: string
}

export interface Document {
  id: string
  title: string
  mime_type: string
  platform: PlatformType
  status: RecordStatus
  tags: string[]
  chunks?: DocumentChunk[]
  uploaded_at: string
  updated_at: string
}

export interface DocumentSearchResult {
  document_id: string
  title: string
  snippet: string
  score: number
  tags: string[]
}

export interface ProcessNode {
  id: string
  process_id: string
  label: string
  type: 'STEP' | 'DECISION' | 'AUTOMATION' | 'MANUAL' | 'INTEGRATION'
  position: { x: number; y: number }
  metadata?: Record<string, unknown>
}

export interface ProcessEdge {
  id: string
  process_id: string
  source: string
  target: string
  label?: string
}

export interface BusinessProcess {
  id: string
  name: string
  description?: string
  health: ProcessHealthStatus
  sub_process_count: number
  asset_count: number
  automation_coverage?: number
  nodes: ProcessNode[]
  edges: ProcessEdge[]
  created_at: string
  updated_at: string
}

export interface RecommendationAction {
  id: string
  title: string
  description?: string
  order: number
}

export interface RecommendationImpact {
  revenue_usd_per_year?: number
  hours_saved_per_month?: number
  risk_reduction?: string
  systems_affected: string[]
}

export interface ArchitectureHealth {
  metadata_sync_pct: number
  process_optimization_pct: number
  data_consistency_pct?: number
  agent_coverage_pct?: number
}

export interface Recommendation {
  id: string
  title: string
  summary: string
  domain: string
  priority: RecommendationPriority
  status: RecommendationLifecycleStatus
  tags: string[]
  actions: RecommendationAction[]
  impact: RecommendationImpact
  architecture_health?: ArchitectureHealth
  estimated_roi_usd_per_year?: number
  created_at: string
  updated_at: string
}

export interface Agent {
  id: string
  name: string
  model: string
  version?: string
  status: AgentRuntimeStatus
  monthly_cap_usd: number
  spend_usd: number
  tags: string[]
  task_count?: number
  accuracy_pct?: number
  token_count?: string
  created_at: string
}

export interface AgentUsageLog {
  id: string
  agent_id: string
  at: string
  task_type: string
  tokens: number
  cost_usd: number
  success: boolean
}

export interface BusinessEntity {
  id: string
  name: string
  type: string
  parent_id?: string
  description?: string
  metadata?: Record<string, unknown>
}

export interface VelocityMetrics {
  objects_analyzed: number
  records_processed: number
  documents_indexed: number
  period: string
}

export interface OrganizationHierarchyNode {
  id: string
  name: string
  title?: string
  children?: OrganizationHierarchyNode[]
}

export interface CostModelSummary {
  total_annual_it_spend_usd: number
  labor_hours_per_year: number
  projected_savings_usd: number
  deflection_rate_pct: number
}

export interface SalesforceInitiateResponse {
  authorization_url: string
  state: string
}

export interface ProcessExportResult {
  url?: string
  format: string
  data?: unknown
}

export interface RecommendationsSummary {
  total: number
  active: number
  implemented: number
  estimated_total_roi_usd: number
}

export interface FleetAnalytics {
  avg_accuracy_pct: number
  efficiency_delta_pct: number
  total_agents: number
  monthly_spend_usd: number
}
