import type {
  Agent,
  AnalysisConfig,
  BusinessEntity,
  ChatAction,
  ChatThread,
  ChatThreadDetail,
  Community,
  DiscoveryStatus,
  Document,
  DocumentChunk,
  DocumentConcept,
  DocumentSearchResult,
  DomainGraphResponse,
  FleetAnalytics,
  GapItem,
  MetadataAutomation,
  MetadataComponent,
  MetadataField,
  MetadataObject,
  MetadataSummary,
  ModelCatalog,
  PaginatedResponse,
  PlatformConnection,
  ProcessHandoffItem,
  ProcessMapSettings,
  PromptBlock,
  PromptOperation,
  ProvenanceLink,
  Recommendation,
  PortfolioProjection,
  RecordTelemetry,
  SalesforceInitiateResponse,
  SyncEvent,
  VelocityMetrics,
} from '@/types'

const API_BASE = (import.meta.env.VITE_API_URL || '') + '/api/v1'

export type TokenGetter = () => Promise<string | null>

let getToken: TokenGetter | null = null

export function setApiTokenGetter(fn: TokenGetter | null) {
  getToken = fn
}

class ApiError extends Error {
  status: number
  body: string

  constructor(message: string, status: number, body: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const raw = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const url = raw
  const headers = new Headers(options.headers)

  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (getToken) {
    const token = await getToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }

  const res = await fetch(url, { ...options, headers })

  if (!res.ok) {
    const text = await res.text()
    throw new ApiError(res.statusText || 'Request failed', res.status, text)
  }

  if (res.status === 204) {
    return undefined as T
  }

  const contentType = res.headers.get('content-type')
  if (contentType?.includes('application/json')) {
    return (await res.json()) as T
  }

  return (await res.text()) as T
}

/** Raw fetch with the same auth + base URL as `request`, for streaming responses. */
export async function fetchWithAuth(path: string, options: RequestInit = {}): Promise<Response> {
  const raw = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
  const headers = new Headers(options.headers)

  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (getToken) {
    const token = await getToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
  }

  return fetch(raw, { ...options, headers })
}

function normalizeChatThreads(raw: unknown): ChatThread[] {
  if (Array.isArray(raw)) return raw as ChatThread[]
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items)) {
    return (raw as { items: ChatThread[] }).items
  }
  return []
}

function withQuery(path: string, params?: Record<string, string | number | boolean | undefined>) {
  if (!params) return path
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) search.set(k, String(v))
  })
  const q = search.toString()
  return q ? `${path}?${q}` : path
}

export const api = {
  connections: {
    list: async (params?: { page?: number; page_size?: number }) => {
      const raw = await request<{ connections: PlatformConnection[]; total: number }>(
        withQuery('/connections', params),
      )
      const items = raw.connections ?? []
      return {
        items,
        total: raw.total ?? items.length,
        page: 1,
        page_size: items.length || 50,
        has_more: false,
      } satisfies PaginatedResponse<PlatformConnection>
    },
    initiateSalesforce: () =>
      request<SalesforceInitiateResponse>('/connections/salesforce/initiate', { method: 'POST' }),
    sync: (id: string) => request<void>(`/connections/${id}/sync`, { method: 'POST' }),
    reauth: (id: string) =>
      request<SalesforceInitiateResponse>(`/connections/${id}/reauth`, { method: 'POST' }),
    delete: (id: string) => request<void>(`/connections/${id}`, { method: 'DELETE' }),
    syncEvents: (id: string, runId?: string) =>
      request<SyncEvent[]>(
        withQuery(`/connections/${id}/sync-events`, runId ? { run_id: runId } : undefined),
      ),
  },
  metadata: {
    listObjects: (params?: { page?: number; page_size?: number; q?: string }) =>
      request<PaginatedResponse<MetadataObject>>(withQuery('/metadata/objects', params)),
    getObject: (id: string) => request<MetadataObject>(`/metadata/objects/${id}`),
    getObjectTelemetry: (id: string) => request<RecordTelemetry[]>(`/metadata/objects/${id}/telemetry`),
    getObjectFields: (id: string) => request<MetadataField[]>(`/metadata/objects/${id}/fields`),
    summary: () => request<MetadataSummary>('/metadata/summary'),
    listAutomation: (params?: { page?: number; page_size?: number }) =>
      request<PaginatedResponse<MetadataAutomation>>(withQuery('/metadata/automation', params)),
    listComponents: (params?: {
      page?: number
      page_size?: number
      component_category?: string
      q?: string
    }) =>
      request<PaginatedResponse<MetadataComponent>>(withQuery('/metadata/components', params)),
    getVelocity: () => request<VelocityMetrics>('/analysis/velocity'),
    updateClassification: (objectId: string, classification: string) =>
      request<unknown>(`/metadata/objects/${objectId}/classification`, {
        method: 'PATCH',
        body: JSON.stringify({ classification }),
      }),
  },
  documents: {
    list: (params?: { page?: number; page_size?: number }) =>
      request<PaginatedResponse<Document>>(withQuery('/documents', params)),
    upload: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<Document>('/documents/upload', { method: 'POST', body })
    },
    get: (id: string) => request<Document>(`/documents/${id}`),
    updateTags: (id: string, tags: string[]) =>
      request<void>(`/documents/${id}/tags`, {
        method: 'PATCH',
        body: JSON.stringify({ tags }),
      }),
    search: (query: string) =>
      request<DocumentSearchResult[]>('/documents/search', {
        method: 'POST',
        body: JSON.stringify({ query }),
      }),
    delete: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
    chunks: (documentId: string) =>
      request<DocumentChunk[]>(`/documents/${documentId}/chunks`),
    concepts: (documentId: string) =>
      request<DocumentConcept[]>(`/documents/${documentId}/concepts`),
    communities: (documentId: string) =>
      request<Community[]>(`/documents/${documentId}/communities`),
    provenance: (documentId: string) =>
      request<ProvenanceLink[]>(`/documents/${documentId}/provenance`),
  },
  processes: {
    list: () => request<unknown>('/processes'),
    get: (id: string) => request<unknown>(`/processes/${id}`),
    create: (data: unknown) =>
      request<unknown>('/processes', { method: 'POST', body: JSON.stringify(data) }),
    updateNodes: (id: string, nodes: unknown) =>
      request<void>(`/processes/${id}/nodes`, { method: 'PUT', body: JSON.stringify(nodes) }),
    generate: () => request<void>('/processes/generate', { method: 'POST' }),
    export: (id: string, format: string) =>
      request<unknown>(`/processes/${id}/export`, {
        method: 'POST',
        body: JSON.stringify({ format }),
      }),
    gaps: () => request<GapItem[] | { items: GapItem[] }>('/processes/gaps').then((raw) => {
      if (Array.isArray(raw)) return raw
      if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: GapItem[] }).items)) {
        return (raw as { items: GapItem[] }).items
      }
      return []
    }),
    updateGap: (id: string, data: Record<string, unknown>) =>
      request<GapItem>(`/processes/gaps/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    domainGraph: (domainId: string) =>
      request<DomainGraphResponse>(`/processes/${domainId}/domain-graph`),
    saveDomainPositions: (domainId: string, positions: Record<string, { x: number; y: number }>) =>
      request<void>(`/processes/${domainId}/domain-graph/positions`, {
        method: 'PUT',
        body: JSON.stringify({ positions }),
      }),
    clearDomainPositions: (domainId: string) =>
      request<void>(`/processes/${domainId}/domain-graph/positions`, {
        method: 'DELETE',
      }),
  },
  chat: {
    listThreads: () => request<unknown>('/chat/threads').then(normalizeChatThreads),
    getThread: (id: string) => request<ChatThreadDetail>(`/chat/threads/${id}`),
    createThread: (body?: {
      title?: string
      anchor_type?: string | null
      anchor_id?: string | null
      model_override?: string | null
    }) => request<ChatThread>('/chat/threads', { method: 'POST', body: JSON.stringify(body ?? {}) }),
    deleteThread: (id: string) => request<void>(`/chat/threads/${id}`, { method: 'DELETE' }),
    /** POST assistant turn; response body is SSE (`text/event-stream`). */
    sendMessageStream: (threadId: string, content: string, signal?: AbortSignal) =>
      fetchWithAuth(`/chat/threads/${threadId}/messages`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream' },
        body: JSON.stringify({ content }),
        signal,
      }),
    confirmAction: (actionId: string, body?: Record<string, unknown>) =>
      request<ChatAction>(`/chat/actions/${actionId}/confirm`, {
        method: 'POST',
        body: JSON.stringify(body ?? {}),
      }),
    rejectAction: (actionId: string) =>
      request<ChatAction>(`/chat/actions/${actionId}/reject`, { method: 'POST' }),
  },
  discovery: {
    start: () => request<void>('/discovery/start', { method: 'POST' }),
    status: () => request<DiscoveryStatus>('/discovery/status'),
    handoffs: () => request<ProcessHandoffItem[]>('/discovery/handoffs'),
    confirmProcess: (id: string) =>
      request<void>(`/discovery/${id}/confirm`, { method: 'POST' }),
    rejectProcess: (id: string) =>
      request<void>(`/discovery/${id}/reject`, { method: 'POST' }),
  },
  recommendations: {
    list: (params?: {
      page?: number
      page_size?: number
      status?: string
      category?: string
      recommendation_type?: string
      automation_type?: string
      sort?: string
    }) => request<PaginatedResponse<Recommendation>>(withQuery('/recommendations', params)),
    get: (id: string) => request<Recommendation>(`/recommendations/${id}`),
    generate: () => request<void>('/recommendations/generate', { method: 'POST' }),
    runs: (params?: { page?: number; page_size?: number }) =>
      request<PaginatedResponse<Record<string, unknown>>>(withQuery('/recommendations/runs', params)),
    recalculate: (id: string, body: { overrides: Record<string, unknown> }) =>
      request<unknown>(`/recommendations/${id}/recalculate`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    updateStatus: (id: string, status: string) =>
      request<void>(`/recommendations/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    summary: () => request<unknown>('/recommendations/summary'),
    portfolioProjection: (recommendation_ids: string[], global_overrides?: Record<string, unknown>) =>
      request<PortfolioProjection>('/recommendations/portfolio-projection', {
        method: 'POST',
        body: JSON.stringify({ recommendation_ids, global_overrides: global_overrides ?? {} }),
      }),
  },
  organization: {
    profile: () => request<unknown>('/organization/profile'),
    hierarchy: () => request<unknown>('/organization/hierarchy'),
    entities: (params?: { page?: number; page_size?: number }) =>
      request<PaginatedResponse<BusinessEntity>>(withQuery('/organization/entities', params)),
    createEntity: (data: unknown) =>
      request<unknown>('/organization/entities', { method: 'POST', body: JSON.stringify(data) }),
    updateEntity: (id: string, data: unknown) =>
      request<unknown>(`/organization/entities/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    costModel: () => request<unknown>('/organization/cost-model'),
    licensing: () => request<Record<string, unknown>>('/organization/licensing'),
    userVelocity: () => request<unknown[]>('/organization/user-velocity'),
    syncFromSalesforce: () =>
      request<void>('/organization/sync-from-salesforce', { method: 'POST' }),
    models: () => request<ModelCatalog>('/organization/models'),
    settings: () => request<unknown>('/organization/settings'),
    updateSettings: (data: Record<string, unknown>) =>
      request<unknown>('/organization/settings', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    updateProfile: (data: Record<string, unknown>) =>
      request<unknown>('/organization/profile', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    startResearch: () =>
      request<{ task_id: string }>('/organization/research', { method: 'POST' }),
    researchStatus: () =>
      request<{ status: string; phase: string | null; progress: number; message: string | null; error: string | null }>('/organization/research/status'),
    researchLatest: () =>
      request<unknown>('/organization/research/latest'),
    reanalyze: () => request<unknown>('/organization/reanalyze', { method: 'POST' }),
    processMapSettings: () =>
      request<ProcessMapSettings>('/organization/process-map-settings'),
    updateProcessMapSettings: (data: ProcessMapSettings) =>
      request<ProcessMapSettings>('/organization/process-map-settings', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
  },
  agents: {
    list: () => request<unknown>('/agents'),
    create: (data: unknown) =>
      request<unknown>('/agents', { method: 'POST', body: JSON.stringify(data) }),
    get: (id: string) => request<unknown>(`/agents/${id}`),
    update: (id: string, data: unknown) =>
      request<unknown>(`/agents/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    usage: (id: string) => request<unknown>(`/agents/${id}/usage`),
    fleetAnalytics: () => request<FleetAnalytics>('/agents/fleet-analytics'),
    delete: (id: string) => request<void>(`/agents/${id}`, { method: 'DELETE' }),
  },
  prompts: {
    operations: () => request<{ operations: PromptOperation[] }>('/prompts/operations'),
    blocks: (operationId: string) => request<PromptBlock[]>(`/prompts/${operationId}`),
    updateBlock: (operationId: string, blockType: string, content: string) =>
      request<PromptBlock>(`/prompts/${operationId}/blocks/${blockType}`, {
        method: 'PUT',
        body: JSON.stringify({ content }),
      }),
    restoreBlock: (operationId: string, blockType: string) =>
      request<PromptBlock>(`/prompts/${operationId}/blocks/${blockType}`, {
        method: 'DELETE',
      }),
    template: (operationId: string, blockType: string) =>
      request<{ content: string }>(`/prompts/templates/${operationId}/${blockType}`),
  },
}
