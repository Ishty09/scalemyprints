'use client'

import { useMutation } from '@tanstack/react-query'

import type {
  TrademarkSearchRequest,
  TrademarkSearchResponse,
} from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

/**
 * React Query mutation for trademark search.
 *
 * Mutation rather than query because:
 * - User explicitly initiates each search
 * - Each search is a discrete event, not server state to keep in sync
 * - Caching is handled server-side; our client always sees fresh results
 */
export function useTrademarkSearch() {
  return useMutation<TrademarkSearchResponse, ApiClientError, TrademarkSearchRequest>({
    mutationKey: ['trademark', 'search'],
    mutationFn: (request) =>
      apiClient.post<TrademarkSearchResponse, TrademarkSearchRequest>(
        '/api/v1/trademark/search',
        request,
      ),
  })
}
