import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { ProcessMapSettings, SyncEvent } from '@/types'

const LEGACY_SYNC_PHASES = [
  'objects',
  'automations',
  'code',
  'permissions',
  'ui_components',
  'installed_packages',
  'licensing',
  'user_velocity',
  'entities',
  'classification',
  'vectorization',
] as const

/** Bridge sync event log to legacy `SyncProgressPanel` shape until the UI is migrated. */
function syncEventsToProgressData(events: SyncEvent[]): {
  status: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  phases?: Record<string, { status: string; count: number }>
} {
  if (!events.length) {
    return { status: 'idle', started_at: null, completed_at: null, error: null }
  }
  const sorted = [...events].sort((a, b) => a.sequence - b.sequence)
  const last = sorted[sorted.length - 1]!

  const terminalError = sorted
    .slice()
    .reverse()
    .find((e) => e.event_type === 'error' && e.severity === 'error')

  let status = 'running'
  if (last.event_type === 'run_complete') status = 'completed'
  else if (terminalError) status = 'failed'

  const started_at = sorted.find((e) => e.event_type === 'run_start')?.created_at ?? sorted[0]!.created_at
  const completed_at = last.event_type === 'run_complete' ? last.created_at : null
  const error = status === 'failed' ? (terminalError?.message ?? 'Sync failed') : null

  const phases: Record<string, { status: string; count: number }> = {}
  if (status === 'completed') {
    for (const p of LEGACY_SYNC_PHASES) {
      phases[p] = { status: 'done', count: 0 }
    }
  }

  return { status, started_at, completed_at, error, phases: Object.keys(phases).length ? phases : undefined }
}

export function useConnections() {
  return useQuery({
    queryKey: ['connections'],
    queryFn: () => api.connections.list(),
  })
}

export function useInitiateSalesforce() {
  return useMutation({
    mutationFn: () => api.connections.initiateSalesforce(),
  })
}

export function useSyncConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.connections.sync(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['connections'] })
      void qc.invalidateQueries({ queryKey: ['metadata'] })
    },
  })
}

export function useDeleteConnection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.connections.delete(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['connections'] })
      void qc.invalidateQueries({ queryKey: ['metadata'] })
    },
  })
}

export function useReauthConnection() {
  return useMutation({
    mutationFn: (id: string) => api.connections.reauth(id),
    onSuccess: (data) => {
      window.location.href = data.authorization_url
    },
  })
}

export function useMetadataObjects(
  params?: { page?: number; page_size?: number; q?: string },
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['metadata', 'objects', params],
    queryFn: () => api.metadata.listObjects(params),
    enabled: options?.enabled ?? true,
  })
}

export function useMetadataObject(id: string) {
  return useQuery({
    queryKey: ['metadata', 'object', id],
    queryFn: () => api.metadata.getObject(id),
    enabled: !!id,
  })
}

export function useObjectTelemetry(id: string) {
  return useQuery({
    queryKey: ['metadata', 'telemetry', id],
    queryFn: () => api.metadata.getObjectTelemetry(id),
    enabled: !!id,
  })
}

export function useObjectFields(id: string) {
  return useQuery({
    queryKey: ['metadata', 'fields', id],
    queryFn: () => api.metadata.getObjectFields(id),
    enabled: !!id,
  })
}

export function useMetadataAutomation(
  params?: { page?: number; page_size?: number },
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['metadata', 'automation', params],
    queryFn: () => api.metadata.listAutomation(params),
    enabled: options?.enabled ?? true,
  })
}

export function useMetadataSummary(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['metadata', 'summary'],
    queryFn: () => api.metadata.summary(),
    enabled: options?.enabled ?? true,
  })
}

export function useMetadataComponents(
  params?: { page?: number; page_size?: number; component_category?: string; q?: string },
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['metadata', 'components', params],
    queryFn: () => api.metadata.listComponents(params),
    enabled: options?.enabled ?? true,
  })
}

export function useOrgProfile() {
  return useQuery({
    queryKey: ['organization', 'profile'],
    queryFn: () => api.organization.profile(),
  })
}

export function useOrgHierarchy() {
  return useQuery({
    queryKey: ['organization', 'hierarchy'],
    queryFn: () => api.organization.hierarchy(),
  })
}

export function useOrgEntities(params?: { page?: number; page_size?: number }) {
  return useQuery({
    queryKey: ['organization', 'entities', params],
    queryFn: () => api.organization.entities(params),
  })
}

export function useCostModel() {
  return useQuery({
    queryKey: ['organization', 'cost-model'],
    queryFn: () => api.organization.costModel(),
  })
}

export function useOrgLicensing() {
  return useQuery({
    queryKey: ['organization', 'licensing'],
    queryFn: () => api.organization.licensing(),
    retry: false,
  })
}

export function useUserVelocity() {
  return useQuery({
    queryKey: ['organization', 'user-velocity'],
    queryFn: () => api.organization.userVelocity(),
    retry: false,
  })
}

export function useUpdateClassification() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ objectId, classification }: { objectId: string; classification: string }) =>
      api.metadata.updateClassification(objectId, classification),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['metadata'] })
    },
  })
}

export function useModelCatalog() {
  return useQuery({
    queryKey: ['organization', 'models'],
    queryFn: () => api.organization.models(),
  })
}

export function useOrgSettings() {
  return useQuery({
    queryKey: ['organization', 'settings'],
    queryFn: () => api.organization.settings(),
  })
}

export function useUpdateOrgSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: Record<string, unknown>) => api.organization.updateSettings(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['organization', 'settings'] })
    },
  })
}

export function useReanalyze() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.organization.reanalyze(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['metadata'] })
    },
  })
}

export function useProcesses() {
  return useQuery({
    queryKey: ['processes'],
    queryFn: () => api.processes.list(),
  })
}

export function useProcess(id: string) {
  return useQuery({
    queryKey: ['processes', id],
    queryFn: () => api.processes.get(id),
    enabled: !!id,
  })
}

export function useGenerateProcesses() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.processes.generate(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processes'] }),
  })
}

export function useRecommendations(params?: { page?: number; page_size?: number; status?: string }) {
  return useQuery({
    queryKey: ['recommendations', params],
    queryFn: () => api.recommendations.list(params),
  })
}

export function useRecommendationSummary() {
  return useQuery({
    queryKey: ['recommendations', 'summary'],
    queryFn: () => api.recommendations.summary(),
  })
}

export function useGenerateRecommendations() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.recommendations.generate(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['recommendations'] }),
  })
}

export function useAgents() {
  return useQuery({
    queryKey: ['agents'],
    queryFn: () => api.agents.list(),
  })
}

export function useFleetAnalytics() {
  return useQuery({
    queryKey: ['agents', 'fleet-analytics'],
    queryFn: () => api.agents.fleetAnalytics(),
  })
}

export function useCreateAgent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: unknown) => api.agents.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      qc.invalidateQueries({ queryKey: ['agents', 'fleet-analytics'] })
    },
  })
}

export function useSyncProgress(connectionId: string | null) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: ['sync-progress', connectionId],
    queryFn: async () => {
      const events = await api.connections.syncEvents(connectionId!)
      return syncEventsToProgressData(events)
    },
    enabled: !!connectionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed') return false
      return 2000
    },
  })

  const status = query.data?.status
  useEffect(() => {
    if (status === 'completed' || status === 'failed') {
      void qc.invalidateQueries({ queryKey: ['connections'] })
      void qc.invalidateQueries({ queryKey: ['metadata'] })
      void qc.invalidateQueries({ queryKey: ['organization'] })
    }
  }, [status, qc])

  return query
}

export function useDiscoveryStatus() {
  return useQuery({
    queryKey: ['discovery-status'],
    queryFn: () => api.discovery.status(),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'completed' || status === 'failed' || status === 'idle') return false
      return 2000
    },
  })
}

export function useStartDiscovery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.discovery.start(),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['discovery-status'] })
    },
  })
}

export function useConfirmProcess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.discovery.confirmProcess(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['processes'] })
      void qc.invalidateQueries({ queryKey: ['discovery-status'] })
    },
  })
}

export function useRejectProcess() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.discovery.rejectProcess(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['processes'] })
      void qc.invalidateQueries({ queryKey: ['discovery-status'] })
    },
  })
}

export function usePromptOperations() {
  return useQuery({
    queryKey: ['prompts', 'operations'],
    queryFn: () => api.prompts.operations(),
  })
}

export function usePromptBlocks(operationId: string | null) {
  return useQuery({
    queryKey: ['prompts', 'blocks', operationId],
    queryFn: () => api.prompts.blocks(operationId!),
    enabled: !!operationId,
  })
}

export function useUpdatePromptBlock() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ operationId, blockType, content }: { operationId: string; blockType: string; content: string }) =>
      api.prompts.updateBlock(operationId, blockType, content),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['prompts', 'blocks', vars.operationId] })
    },
  })
}

export function useRestorePromptBlock() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ operationId, blockType }: { operationId: string; blockType: string }) =>
      api.prompts.restoreBlock(operationId, blockType),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['prompts', 'blocks', vars.operationId] })
    },
  })
}

export function usePromptTemplate(operationId: string, blockType: string) {
  return useQuery({
    queryKey: ['prompts', 'template', operationId, blockType],
    queryFn: () => api.prompts.template(operationId, blockType),
    staleTime: 5 * 60 * 1000,
  })
}

export function useDomainGraph(domainId: string) {
  return useQuery({
    queryKey: ['processes', 'domain-graph', domainId],
    queryFn: () => api.processes.domainGraph(domainId),
    enabled: !!domainId,
  })
}

export function useProcessMapSettings() {
  return useQuery({
    queryKey: ['organization', 'process-map-settings'],
    queryFn: () => api.organization.processMapSettings(),
  })
}

export function useUpdateProcessMapSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ProcessMapSettings) => api.organization.updateProcessMapSettings(data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['organization', 'process-map-settings'] }),
  })
}

export function useSaveDomainPositions() {
  return useMutation({
    mutationFn: ({ domainId, positions }: { domainId: string; positions: Record<string, { x: number; y: number }> }) =>
      api.processes.saveDomainPositions(domainId, positions),
  })
}

export function useClearDomainPositions(domainId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.processes.clearDomainPositions(domainId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['processes', 'domain-graph', domainId] }),
  })
}
