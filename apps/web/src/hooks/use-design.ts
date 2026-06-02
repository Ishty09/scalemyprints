'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  DesignGenerateBody,
  DesignJob,
  DesignJobListResponse,
  DesignQuota,
  DesignStatus,
  DesignStylePreset,
} from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

const DESIGN_KEY = ['design'] as const

/**
 * Mutation: submit a new design generation request.
 *
 * The backend runs synchronously (~3-15s). Loading state is owned by
 * the caller; we invalidate the jobs/quota cache on settle so the
 * gallery and quota badge refresh.
 */
export function useGenerateDesign() {
  const queryClient = useQueryClient()

  return useMutation<DesignJob, ApiClientError, DesignGenerateBody>({
    mutationKey: [...DESIGN_KEY, 'generate'],
    mutationFn: (body) =>
      apiClient.post<DesignJob, DesignGenerateBody>('/api/v1/design/generate', body),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [...DESIGN_KEY, 'jobs'] })
      queryClient.invalidateQueries({ queryKey: [...DESIGN_KEY, 'quota'] })
    },
  })
}

/**
 * Mutation: iterate on a previous design.
 */
export function useIterateDesign(parentJobId: string) {
  const queryClient = useQueryClient()
  return useMutation<DesignJob, ApiClientError, DesignGenerateBody>({
    mutationKey: [...DESIGN_KEY, 'iterate', parentJobId],
    mutationFn: (body) =>
      apiClient.post<DesignJob, DesignGenerateBody>(
        `/api/v1/design/jobs/${parentJobId}/iterate`,
        body,
      ),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [...DESIGN_KEY, 'jobs'] })
      queryClient.invalidateQueries({ queryKey: [...DESIGN_KEY, 'quota'] })
    },
  })
}

/**
 * Query: paginated list of jobs.
 */
export function useDesignJobs(params: {
  limit?: number
  offset?: number
  status?: DesignStatus
}) {
  const { limit = 20, offset = 0, status } = params
  return useQuery<DesignJobListResponse, ApiClientError>({
    queryKey: [...DESIGN_KEY, 'jobs', { limit, offset, status }],
    queryFn: () => {
      const search = new URLSearchParams()
      search.set('limit', String(limit))
      search.set('offset', String(offset))
      if (status) search.set('status', status)
      return apiClient.get<DesignJobListResponse>(
        `/api/v1/design/jobs?${search.toString()}`,
      )
    },
    staleTime: 30 * 1000,
  })
}

/**
 * Query: single job. Polls every 2s while in a non-terminal state.
 */
export function useDesignJob(jobId: string | null | undefined) {
  return useQuery<DesignJob, ApiClientError>({
    queryKey: [...DESIGN_KEY, 'jobs', jobId],
    enabled: Boolean(jobId),
    queryFn: () => apiClient.get<DesignJob>(`/api/v1/design/jobs/${jobId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status) return false
      const TERMINAL: DesignStatus[] = ['completed', 'failed', 'cancelled']
      return TERMINAL.includes(status) ? false : 2_000
    },
  })
}

/**
 * Mutation: soft-delete a job.
 */
export function useDeleteDesignJob() {
  const queryClient = useQueryClient()
  return useMutation<{ id: string; deleted: boolean }, ApiClientError, string>({
    mutationKey: [...DESIGN_KEY, 'delete'],
    mutationFn: (jobId) =>
      apiClient.delete<{ id: string; deleted: boolean }>(
        `/api/v1/design/jobs/${jobId}`,
      ),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [...DESIGN_KEY, 'jobs'] })
    },
  })
}

/**
 * Query: current quota snapshot.
 */
export function useDesignQuota() {
  return useQuery<DesignQuota, ApiClientError>({
    queryKey: [...DESIGN_KEY, 'quota'],
    queryFn: () => apiClient.get<DesignQuota>('/api/v1/design/quota'),
    staleTime: 60 * 1000,
  })
}

/**
 * Query: style preset metadata for the chip selector.
 */
export function useDesignStyles() {
  return useQuery<DesignStylePreset[], ApiClientError>({
    queryKey: [...DESIGN_KEY, 'styles'],
    queryFn: () => apiClient.get<DesignStylePreset[]>('/api/v1/design/styles'),
    staleTime: 24 * 60 * 60 * 1000, // 1 day — these don't change
  })
}
