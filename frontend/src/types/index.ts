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

export interface AnalysisConfig {
  velocity_window_days: number
  classification_threshold: number
  min_records_for_vectorization: number
  embedding_provider: string
  vector_store_provider: string
  llm_provider: string
  model_overrides?: Record<string, string>
}

export interface ModelProviderModel {
  id: string
  model_id: string
  label: string
  tier_default: string
}

export interface ModelProvider {
  id: string
  name: string
  models: ModelProviderModel[]
}

export interface ModelOperation {
  id: string
  label: string
  group: string
  group_label: string
  description: string
  default_tier: string
  thinking_budget: number
  output_format: 'json' | 'text' | 'none'
  effective_model: string
  effective_provider: string
}

export interface ModelCatalog {
  providers: ModelProvider[]
  operations: ModelOperation[]
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
  platform_org_id?: string | null
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
  classification?: string | null
  classification_source?: string
  velocity_score?: number
  automation_count?: number
  metadata_json?: Record<string, unknown>
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

/** Row from `GET /metadata/automation` (paginated). */
export interface MetadataAutomation {
  id: string
  connection_id: string
  org_id: string
  automation_type: string
  api_name: string
  label: string | null
  status: string | null
  related_object: string | null
  complexity_score: number | null
  metadata_json: Record<string, unknown>
}

export interface MetadataComponent {
  id: string
  org_id: string
  connection_id: string
  component_category: string
  api_name: string
  label: string | null
  status: string | null
  related_object: string | null
  metadata_json: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface MetadataSummary {
  objects: { total: number; custom: number; with_records: number }
  fields: { total: number; custom: number }
  automations: Record<string, number>
  components: Record<string, number>
  licensing: {
    edition?: string
    total_licenses?: number
    used_licenses?: number
    estimated_annual_spend?: number | null
  }
  last_sync_at: string | null
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

export interface DiscoveryPhase {
  status: string
  count: number
  total: number
}

export interface DiscoveryStatus {
  run_id: string | null
  status: string
  phases: Record<string, DiscoveryPhase>
  started_at: string | null
  completed_at: string | null
  error: string | null
}

export interface ProcessHandoffItem {
  id: string
  source_process_id: string
  target_process_id: string
  handoff_type: string
  description: string | null
  confidence_score: number
  is_gap: boolean
  needs_review: boolean
  gap_status: string
  resolution_note: string | null
}

export interface ChatThread {
  id: string
  org_id: string
  user_id: string
  title: string
  anchor_type: string | null
  anchor_id: string | null
  model_override: string | null
  summary: string | null
  message_count: number
  status: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  thread_id: string
  role: 'user' | 'assistant' | 'system' | 'tool_result'
  content: string
  tool_calls: unknown[]
  tool_results: unknown[]
  token_count: number | null
  langfuse_trace_id: string | null
  created_at: string
}

export interface ChatAction {
  id: string
  thread_id: string
  message_id: string
  action_type: string
  target_id: string | null
  payload: Record<string, unknown>
  status: 'proposed' | 'confirmed' | 'executed' | 'rejected' | 'failed'
  result: Record<string, unknown> | null
  idempotency_key: string
  created_at: string
  executed_at: string | null
}

export interface ChatThreadDetail {
  thread: ChatThread
  messages: ChatMessage[]
  pending_actions: ChatAction[]
}

export interface GapItem {
  id: string
  source_process_id: string
  target_process_id: string
  source_process_name: string
  target_process_name: string
  source_domain_name: string | null
  target_domain_name: string | null
  handoff_type: string
  description: string | null
  confidence_score: number
  gap_status: 'open' | 'investigating' | 'resolved'
  resolution_note: string | null
  is_gap: boolean
  needs_review: boolean
}

export type QuickOption = { id: string; label: string }
export type CardOption = { id: string; label: string; description: string }

export type ArcResponse =
  | { type: 'message'; text: string }
  | { type: 'question'; text: string; question: string; options: QuickOption[] }
  | { type: 'card_question'; text: string; question: string; options: CardOption[] }
  | { type: 'action_proposal'; text: string; action_type: string; payload: Record<string, unknown> }
  | { type: 'summary'; text: string; findings: string[]; next_steps: string[] }

export interface PromptBlockInfo {
  type: string
  label: string
  editable: boolean
}

export interface PromptOperation {
  operation_id: string
  label: string
  group: string
  blocks: PromptBlockInfo[]
}

export interface PromptBlock {
  block_type: string
  label: string
  editable: boolean
  content: string
  is_customized: boolean
  is_locked: boolean
  available_vars: string[]
  version: number
}
