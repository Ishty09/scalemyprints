'use client'

import { Calendar, Radar } from 'lucide-react'
import Link from 'next/link'
import { toast } from 'sonner'

import type { NicheSearchRequest } from '@scalemyprints/contracts'

import { NicheResults } from '@/components/app/niche-results'
import { NicheSearchForm } from '@/components/app/niche-search-form'
import { useNicheSearch } from '@/hooks/use-niche'
import { ApiClientError } from '@/lib/api-client'

export default function NicheRadarDashboardPage() {
  const search = useNicheSearch()

  function handleSearch(request: NicheSearchRequest) {
    search.mutate(request, {
      onError: (error) => {
        if (error instanceof ApiClientError) {
          if (error.code === 'rate_limited') {
            toast.error('Too many searches. Wait a minute and try again.')
            return
          }
          if (error.code === 'quota_exceeded') {
            toast.error('Monthly limit reached. Upgrade to continue.')
            return
          }
        }
        toast.error('Niche analysis failed. Please try again.')
      },
    })
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-8">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Radar className="h-7 w-7 text-primary-600" aria-hidden="true" />
            <h1 className="font-display text-3xl font-bold text-slate-900">Niche Radar</h1>
          </div>
          <Link
            href="/dashboard/niche-radar/events"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <Calendar className="h-4 w-4" aria-hidden="true" />
            Events calendar
          </Link>
        </div>
        <p className="text-slate-600">
          Score any niche on demand, trend, competition, profitability, and seasonality.
          Find what to design before everyone else does.
        </p>
      </header>

      <NicheSearchForm onSearch={handleSearch} isLoading={search.isPending} />

      {search.isPending && (
        <div className="mt-8 rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
          Checking Google Trends and marketplace data...
        </div>
      )}

      {search.data && !search.isPending && (
        <div className="mt-8">
          <NicheResults record={search.data} />
        </div>
      )}

      {!search.data && !search.isPending && (
        <section className="mt-8 rounded-xl border border-dashed border-slate-200 bg-white/50 p-8 text-center">
          <Radar className="mx-auto mb-3 h-10 w-10 text-slate-300" aria-hidden="true" />
          <h2 className="mb-1 font-display text-lg font-semibold text-slate-700">
            Discover your next winner
          </h2>
          <p className="mx-auto max-w-md text-sm text-slate-500">
            Enter a niche keyword to see its Niche Health Score across demand, trends,
            competition, profitability, and upcoming events.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2 text-xs">
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">Try: dog mom</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">Try: pickleball dad</span>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">Try: book lover</span>
          </div>
        </section>
      )}
    </div>
  )
}
