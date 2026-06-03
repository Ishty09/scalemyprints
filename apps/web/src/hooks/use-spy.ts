'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type {
  AdLibraryResponse,
  HotMoversResponse,
  ProfitBody,
  ProfitResponse,
  ReverseImageResponse,
  SaturationBody,
  SaturationResponse,
  ShopAuditBody,
  ShopAuditResponse,
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

/**
 * Phase 2: shop teardown.
 */
export function useShopAudit() {
  return useMutation<ShopAuditResponse, ApiClientError, ShopAuditBody>({
    mutationKey: [...SPY_KEY, 'shop-audit'],
    mutationFn: (body) =>
      apiClient.post<ShopAuditResponse, ShopAuditBody>('/api/v1/spy/shop-audit', body),
  })
}

/**
 * Phase 2: saturation/difficulty score.
 */
export function useSaturation() {
  return useMutation<SaturationResponse, ApiClientError, SaturationBody>({
    mutationKey: [...SPY_KEY, 'saturation'],
    mutationFn: (body) =>
      apiClient.post<SaturationResponse, SaturationBody>('/api/v1/spy/saturation', body),
  })
}

/**
 * Phase 2: profit calculator (server-side single-source-of-truth math).
 */
export function useProfit() {
  return useMutation<ProfitResponse, ApiClientError, ProfitBody>({
    mutationKey: [...SPY_KEY, 'profit'],
    mutationFn: (body) =>
      apiClient.post<ProfitResponse, ProfitBody>('/api/v1/spy/profit', body),
  })
}

/**
 * Phase 2: Facebook Ad Library search.
 */
export function useFbAds(params: {
  keyword?: string | null
  pageHandle?: string | null
  country?: string
  limit?: number
  enabled?: boolean
}) {
  const { keyword, pageHandle, country = 'ALL', limit = 25, enabled = true } = params
  return useQuery<AdLibraryResponse, ApiClientError>({
    queryKey: [...SPY_KEY, 'fb-ads', { keyword, pageHandle, country, limit }],
    enabled: enabled && Boolean(keyword || pageHandle),
    queryFn: () => {
      const search = new URLSearchParams()
      if (keyword) search.set('keyword', keyword)
      if (pageHandle) search.set('page_handle', pageHandle)
      search.set('country', country)
      search.set('limit', String(limit))
      return apiClient.get<AdLibraryResponse>(`/api/v1/spy/ads?${search.toString()}`)
    },
    staleTime: 5 * 60 * 1000,
  })
}
