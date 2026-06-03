'use client'

import { Building2, Loader2 } from 'lucide-react'
import { useState } from 'react'

import type { Marketplace, ShopAuditResponse } from '@scalemyprints/contracts'
import { MARKETPLACE_LABELS, MARKETPLACES } from '@scalemyprints/contracts'

import { useShopAudit } from '@/hooks/use-spy'

import { SpyListingCard } from './spy-listing-card'

export function SpyShopAuditPanel() {
  const audit = useShopAudit()
  const [marketplace, setMarketplace] = useState<Marketplace>('etsy')
  const [handle, setHandle] = useState('')
  const [depth, setDepth] = useState<'shallow' | 'standard' | 'deep'>('standard')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = handle.trim()
    if (!trimmed) return
    audit.mutate({ marketplace, handle: trimmed, depth })
  }

  const data: ShopAuditResponse | undefined = audit.data

  return (
    <section className="space-y-4">
      <form
        onSubmit={handleSubmit}
        className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
      >
        <header className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-primary-600" aria-hidden />
          <h2 className="font-display text-lg font-bold text-slate-900">Shop teardown</h2>
        </header>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
          <select
            value={marketplace}
            onChange={(e) => setMarketplace(e.target.value as Marketplace)}
            className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          >
            {MARKETPLACES.filter((m) =>
              ['etsy', 'amazon_merch', 'redbubble'].includes(m),
            ).map((m) => (
              <option key={m} value={m}>
                {MARKETPLACE_LABELS[m]}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            placeholder="Shop handle or URL"
            className="sm:col-span-2 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
          <div className="flex gap-2">
            <select
              value={depth}
              onChange={(e) =>
                setDepth(e.target.value as 'shallow' | 'standard' | 'deep')
              }
              className="flex-1 rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="shallow">Shallow</option>
              <option value="standard">Standard</option>
              <option value="deep">Deep</option>
            </select>
            <button
              type="submit"
              disabled={audit.isPending || !handle.trim()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {audit.isPending && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              )}
              Audit
            </button>
          </div>
        </div>
      </form>

      {data && (
        <article className="space-y-4">
          <header className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="font-display text-lg font-bold text-slate-900">
              {data.shop.display_name ?? data.shop.handle}
            </h3>
            <p className="text-sm text-slate-500">
              <a
                href={data.shop.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary-700 hover:underline"
              >
                {data.shop.url}
              </a>
              {data.shop.location ? ` · ${data.shop.location}` : ''}
            </p>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Stat
                label="Est. monthly revenue"
                value={
                  data.est_monthly_revenue_usd != null
                    ? `$${data.est_monthly_revenue_usd.toLocaleString()}`
                    : '—'
                }
              />
              <Stat
                label="Avg price"
                value={
                  data.avg_price_usd != null ? `$${data.avg_price_usd.toFixed(2)}` : '—'
                }
              />
              <Stat label="Listings sampled" value={data.listings_sampled.toString()} />
              <Stat
                label="New listings (30d)"
                value={(data.new_listings_last_30d ?? 0).toString()}
              />
            </dl>
          </header>

          {data.most_used_tags.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h4 className="mb-2 text-sm font-semibold text-slate-700">Top tags</h4>
              <div className="flex flex-wrap gap-2">
                {data.most_used_tags.map((t) => (
                  <span
                    key={t.tag}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                  >
                    {t.tag}{' '}
                    <span className="text-slate-400">×{t.count}</span>
                  </span>
                ))}
              </div>
            </section>
          )}

          {data.top_listings.length > 0 && (
            <section>
              <h4 className="mb-2 text-sm font-semibold text-slate-700">Top sellers</h4>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
                {data.top_listings.map((l) => (
                  <SpyListingCard
                    key={`${l.marketplace}-${l.external_id}`}
                    listing={l}
                  />
                ))}
              </div>
            </section>
          )}

          {data.error && (
            <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              {data.error}
            </p>
          )}
        </article>
      )}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="font-semibold text-slate-900">{value}</dd>
    </div>
  )
}
