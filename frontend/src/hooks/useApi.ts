import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'

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
