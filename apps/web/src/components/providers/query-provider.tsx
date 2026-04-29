'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useState, type ReactNode } from 'react'

import { ApiClientError } from '@/lib/api-client'

/**
 * Global React Query configuration.
 *
 * Key decisions:
 * - Retry only on 5xx and network errors (never on 4xx — they won't fix themselves)
 * - 30s default stale time (feels snappy but avoids hammering APIs)
 * - Refetch on focus disabled (too noisy for a dashboard)
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry(failureCount, error) {
          if (error instanceof ApiClientError) {
            // Don't retry client errors
            if (error.status >= 400 && error.status < 500) return false
          }
          return failureCount < 2
        },
      },
      mutations: {
        retry: false,
      },
    },
  })
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(createQueryClient)
  return (
    <QueryClientProvider client={client}>
      {children}
      {process.env.NODE_ENV !== 'production' && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}
