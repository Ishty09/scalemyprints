'use client'

import { Shield } from 'lucide-react'
import { toast } from 'sonner'

import type { TrademarkSearchRequest } from '@scalemyprints/contracts'

import { TrademarkResults } from '@/components/app/trademark-results'
import { TrademarkSearchForm } from '@/components/app/trademark-search-form'
import { useTrademarkSearch } from '@/hooks/use-trademark-search'
import { ApiClientError } from '@/lib/api-client'

export default function TrademarkDashboardPage() {
  const search = useTrademarkSearch()

  function handleSearch(request: TrademarkSearchRequest) {
    search.mutate(request, {
      onError: (error) => {
        if (error instanceof ApiClientError) {
          if (error.code === 'rate_limited') {
            toast.error('Too many searches. Please wait a moment.')
            return
          }
          if (error.code === 'quota_exceeded') {
            toast.error('Monthly limit reached. Upgrade to continue searching.')
            return
          }
        }
        toast.error('Search failed. Please try again.')
      },
    })
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8">
        <div className="mb-2 flex items-center gap-3">
          <Shield className="h-7 w-7 text-primary-600" aria-hidden="true" />
          <h1 className="font-display text-3xl font-bold text-slate-900">Trademark Shield</h1>
        </div>
        <p className="text-slate-600">
          Check if your phrase is trademark-safe across US, EU, UK, and Australia before you list.
        </p>
      </header>

      <TrademarkSearchForm onSearch={handleSearch} isLoading={search.isPending} />

      {search.data && (
        <div className="mt-8">
          <TrademarkResults result={search.data} />
        </div>
      )}
    </div>
  )
}
