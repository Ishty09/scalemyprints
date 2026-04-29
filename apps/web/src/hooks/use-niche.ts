'use client'

import { useMutation, useQuery } from '@tanstack/react-query'

import type {
  EventListResponse,
  NicheCountry,
  NicheExpansionRequest,
  NicheExpansionResponse,
  NicheSearchRequest,
  NicheSearchResponse,
} from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

/**
 * Mutation: analyze a niche keyword across all signals.
 */
export function useNicheSearch() {
  return useMutation<NicheSearchResponse, ApiClientError, NicheSearchRequest>({
    mutationKey: ['niche', 'search'],
    mutationFn: (request) =>
      apiClient.post<NicheSearchResponse, NicheSearchRequest>(
        '/api/v1/niche/search',
        request,
      ),
  })
}

/**
 * Query: list upcoming events for a country in a window.
 *
 * Defaults: today → today+90 days. Cached for 1 hour client-side
 * (server caches the static DB lookup for free).
 */
export function useNicheEvents(params: {
  country: NicheCountry
  from?: string
  to?: string
  category?: string
  enabled?: boolean
}) {
  const { country, from, to, category, enabled = true } = params
  return useQuery<EventListResponse, ApiClientError>({
    queryKey: ['niche', 'events', country, from, to, category],
    enabled,
    staleTime: 60 * 60 * 1000, // 1 hour
    queryFn: () => {
      const search = new URLSearchParams()
      search.set('country', country)
      if (from) search.set('from', from)
      if (to) search.set('to', to)
      if (category) search.set('category', category)
      return apiClient.get<EventListResponse>(
        `/api/v1/niche/events?${search.toString()}`,
      )
    },
  })
}

/**
 * Mutation: LLM niche expansion (sub-niche idea generation).
 */
export function useNicheExpansion() {
  return useMutation<NicheExpansionResponse, ApiClientError, NicheExpansionRequest>({
    mutationKey: ['niche', 'expand'],
    mutationFn: (request) =>
      apiClient.post<NicheExpansionResponse, NicheExpansionRequest>(
        '/api/v1/niche/expand',
        request,
      ),
  })
}
