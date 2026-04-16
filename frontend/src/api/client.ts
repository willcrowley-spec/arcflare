import type {
  Agent,
  BusinessEntity,
  Document,
  DocumentSearchResult,
  FleetAnalytics,
  MetadataAutomation,
  MetadataField,
  MetadataObject,
  PaginatedResponse,
  PlatformConnection,
  Recommendation,
  RecordTelemetry,
  SalesforceInitiateResponse,
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
  const url = `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
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
    delete: (id: string) => request<void>(`/connections/${id}`, { method: 'DELETE' }),
  },
  metadata: {
    listObjects: (params?: { page?: number; page_size?: number; q?: string }) =>
      request<PaginatedResponse<MetadataObject>>(withQuery('/metadata/objects', params)),
    getObject: (id: string) => request<MetadataObject>(`/metadata/objects/${id}`),
    getObjectTelemetry: (id: string) => request<RecordTelemetry[]>(`/metadata/objects/${id}/telemetry`),
    getObjectFields: (id: string) => request<MetadataField[]>(`/metadata/objects/${id}/fields`),
    listAutomation: () => request<MetadataAutomation[]>('/metadata/automation'),
    getVelocity: () => request<VelocityMetrics>('/analysis/velocity'),
  },
  documents: {
    list: (params?: { page?: number; page_size?: number }) =>
      request<PaginatedResponse<Document>>(withQuery('/documents', params)),
    upload: (file: File) => {
      const body = new FormData()
      body.append('file', file)
      return request<Document>('/documents', { method: 'POST', body })
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
  },
  recommendations: {
    list: (params?: { page?: number; page_size?: number; status?: string }) =>
      request<PaginatedResponse<Recommendation>>(withQuery('/recommendations', params)),
    get: (id: string) => request<Recommendation>(`/recommendations/${id}`),
    generate: () => request<void>('/recommendations/generate', { method: 'POST' }),
    updateStatus: (id: string, status: string) =>
      request<void>(`/recommendations/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }),
    summary: () => request<unknown>('/recommendations/summary'),
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
    syncFromSalesforce: () =>
      request<void>('/organization/sync-from-salesforce', { method: 'POST' }),
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
}
