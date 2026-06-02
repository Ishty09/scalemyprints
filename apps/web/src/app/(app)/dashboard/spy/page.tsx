'use client'

import { Flame, Radar, Search, Telescope } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import type {
  Marketplace,
  SpyListingItem,
  SpySearchResponse,
  ReverseImageResponse,
} from '@scalemyprints/contracts'
import { MARKETPLACE_LABELS } from '@scalemyprints/contracts'

import { SpyListingCard } from '@/components/app/spy-listing-card'
import { SpyReverseImageUploader } from '@/components/app/spy-reverse-image-uploader'
import { SpySearchForm } from '@/components/app/spy-search-form'
import {
  useSpyHotMovers,
  useSpyReverseImage,
  useSpySearch,
} from '@/hooks/use-spy'

type Tab = 'search' | 'reverse' | 'feed'

export default function SpyPage() {
  const [tab, setTab] = useState<Tab>('search')
  const search = useSpySearch()
  const reverse = useSpyReverseImage()
  const feed = useSpyHotMovers(30)

  const lastSearch: SpySearchResponse | undefined = search.data
  const lastReverse: ReverseImageResponse | undefined = reverse.data

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="mb-6">
        <div className="mb-2 flex items-center gap-3">
          <Radar className="h-7 w-7 text-primary-600" aria-hidden />
          <h1 className="font-display text-3xl font-bold text-slate-900">Spy</h1>
        </div>
        <p className="text-slate-600">
          Cross-marketplace POD intelligence. Search live listings, reverse-image
          across platforms, and watch velocity spikes as they happen.
        </p>
      </header>

      <nav className="mb-6 flex gap-2 border-b border-slate-200">
        {(
          [
            { id: 'search', label: 'Search', icon: Search },
            { id: 'reverse', label: 'Reverse Image', icon: Telescope },
            { id: 'feed', label: 'Hot Movers', icon: Flame },
          ] as { id: Tab; label: string; icon: typeof Search }[]
        ).map((t) => {
          const active = tab === t.id
          const Icon = t.icon
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-semibold transition ${
                active
                  ? 'border-primary-600 text-primary-700'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {t.label}
            </button>
          )
        })}
      </nav>

      {tab === 'search' && (
        <section className="space-y-6">
          <SpySearchForm
            isLoading={search.isPending}
            onSubmit={(body) => {
              search.mutate(body, {
                onError: () => toast.error('Spy search failed. Try again.'),
              })
            }}
          />
          {lastSearch && (
            <ResultsBlock
              total={lastSearch.total}
              listings={lastSearch.listings}
              sourcesUsed={lastSearch.sources_used}
              sourcesFailed={lastSearch.sources_failed.map((f) => ({
                marketplace: f.marketplace,
                error: f.error,
              }))}
              durationMs={lastSearch.duration_ms}
            />
          )}
        </section>
      )}

      {tab === 'reverse' && (
        <section className="space-y-6">
          <SpyReverseImageUploader
            isLoading={reverse.isPending}
            onSubmit={(file) => {
              reverse.mutate(
                { file },
                {
                  onError: () => toast.error('Reverse image search failed.'),
                },
              )
            }}
          />
          {lastReverse && (
            <ReverseResultsBlock data={lastReverse} />
          )}
        </section>
      )}

      {tab === 'feed' && (
        <section>
          {feed.isLoading && (
            <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
              Loading hot movers…
            </div>
          )}
          {!feed.isLoading && (feed.data?.items.length ?? 0) === 0 && (
            <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
              No spikes detected yet. Hot Movers updates every 60s as data is
              collected from background cron jobs.
            </div>
          )}
          {(feed.data?.items.length ?? 0) > 0 && (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
              {feed.data?.items.map((item) => (
                <SpyListingCard
                  key={item.id}
                  listing={hotMoverAsListing(item)}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

function ResultsBlock({
  total,
  listings,
  sourcesUsed,
  sourcesFailed,
  durationMs,
}: {
  total: number
  listings: SpyListingItem[]
  sourcesUsed: Marketplace[]
  sourcesFailed: { marketplace: Marketplace; error: string }[]
  durationMs: number
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          {total} listing{total === 1 ? '' : 's'} · {durationMs} ms ·{' '}
          {sourcesUsed.map((s) => MARKETPLACE_LABELS[s]).join(', ') || 'no source'}
        </span>
        {sourcesFailed.length > 0 && (
          <span className="text-rose-600">
            Failed: {sourcesFailed.map((f) => MARKETPLACE_LABELS[f.marketplace]).join(', ')}
          </span>
        )}
      </div>
      {total === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
          No matches yet. Tip: try a popular niche phrase like
          &ldquo;cottagecore mushroom&rdquo;.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {listings.map((l) => (
            <SpyListingCard key={`${l.marketplace}-${l.external_id}`} listing={l} />
          ))}
        </div>
      )}
    </div>
  )
}

function ReverseResultsBlock({ data }: { data: ReverseImageResponse }) {
  if (data.error) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        {data.error}
      </div>
    )
  }
  if (data.matches.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
        No near-duplicates found. Your design might be fresh — or the index is
        still small while data collection ramps up.
      </div>
    )
  }
  return (
    <div className="space-y-3">
      <div className="text-xs text-slate-500">
        {data.matches.length} match{data.matches.length === 1 ? '' : 'es'} · {data.duration_ms} ms · sha256{' '}
        <code className="text-slate-400">{data.query_sha256.slice(0, 12)}…</code>
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
        {data.matches.map((m) => (
          <SpyListingCard
            key={`${m.listing.marketplace}-${m.listing.external_id}`}
            listing={m.listing}
            badge={`${m.score} · ${m.match_type.replace('_', ' ')}`}
          />
        ))}
      </div>
    </div>
  )
}

function hotMoverAsListing(item: {
  id: string
  marketplace: Marketplace
  title: string
  url: string
  thumbnail_url: string | null
  shop_handle: string | null
  shop_url: string | null
  velocity_class: SpyListingItem['velocity_class']
  est_daily_sales: number | null
  price_usd: number | null
  favorites: number | null
  reviews_count: number | null
  last_seen_at: string
}): SpyListingItem {
  return {
    marketplace: item.marketplace,
    external_id: item.id,
    url: item.url,
    title: item.title,
    description: null,
    tags: [],
    price_usd: item.price_usd,
    currency: 'USD',
    thumbnail_url: item.thumbnail_url,
    shop_handle: item.shop_handle,
    shop_url: item.shop_url,
    status: 'active',
    favorites: item.favorites,
    reviews_count: item.reviews_count,
    rating: null,
    est_daily_sales: item.est_daily_sales,
    velocity_class: item.velocity_class,
    first_seen_at: item.last_seen_at,
    last_seen_at: item.last_seen_at,
  }
}
