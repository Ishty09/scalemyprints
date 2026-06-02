'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  HotMoversResponse,
  ReverseImageResponse,
  SpyListingItem,
  SpySearchBody,
  SpySearchResponse,
} from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

const SPY_KEY = ['spy'] as const

/**
 * Multi-marketplace text/URL search.
 *
 * Mutation rather than query because it's expensive (scrapes 3+
 * marketplaces in parallel) and we only want to fire on explicit
 * user action.
 */
export function useSpySearch() {
  const queryClient = useQueryClient()
  return useMutation<SpySearchResponse, ApiClientError, SpySearchBody>({
    mutationKey: [...SPY_KEY, 'search'],
    mutationFn: (body) =>
      apiClient.post<SpySearchResponse, SpySearchBody>('/api/v1/spy/search', body),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: [...SPY_KEY, 'feed'] })
    },
  })
}

/**
 * Reverse image search — multipart upload, returns ranked matches.
 */
export function useSpyReverseImage() {
  return useMutation<
    ReverseImageResponse,
    ApiClientError,
    { file: File; limit?: number; minClipCosine?: number }
  >({
    mutationKey: [...SPY_KEY, 'reverse-image'],
    mutationFn: async ({ file, limit = 30, minClipCosine = 0.7 }) => {
      const form = new FormData()
      form.append('file', file)
      const search = new URLSearchParams({
        limit: String(limit),
        min_clip_cosine: String(minClipCosine),
      })
      return apiClient.postForm<ReverseImageResponse>(
        `/api/v1/spy/reverse-image?${search.toString()}`,
        form,
      )
    },
  })
}

/**
 * Hot movers feed — listings flagged rising/spiking/explosive in the
 * last 7 days. Refreshes every 60s.
 */
export function useSpyHotMovers(limit = 30) {
  return useQuery<HotMoversResponse, ApiClientError>({
    queryKey: [...SPY_KEY, 'feed', { limit }],
    queryFn: () =>
      apiClient.get<HotMoversResponse>(`/api/v1/spy/feed?limit=${limit}`),
    staleTime: 60 * 1000,
    refetchInterval: 60 * 1000,
  })
}

/**
 * Single listing by spy_listings.id.
 */
export function useSpyListing(listingId: string | null | undefined) {
  return useQuery<SpyListingItem, ApiClientError>({
    queryKey: [...SPY_KEY, 'listing', listingId],
    enabled: Boolean(listingId),
    queryFn: () => apiClient.get<SpyListingItem>(`/api/v1/spy/listing/${listingId}`),
  })
}
