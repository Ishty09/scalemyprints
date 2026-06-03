'use client'

import { ExternalLink, Heart, Star, TrendingUp, Zap } from 'lucide-react'
import Image from 'next/image'

import type { SpyListingItem, VelocityClass } from '@scalemyprints/contracts'
import { MARKETPLACE_LABELS, VELOCITY_LABELS } from '@scalemyprints/contracts'

const VELOCITY_STYLES: Record<VelocityClass, string> = {
  dormant: 'bg-slate-100 text-slate-600',
  steady: 'bg-slate-100 text-slate-600',
  rising: 'bg-amber-100 text-amber-800',
  spiking: 'bg-orange-100 text-orange-800',
  explosive: 'bg-rose-100 text-rose-800',
}

export function SpyListingCard({
  listing,
  badge,
}: {
  listing: SpyListingItem
  /** Optional badge override (e.g., match score) shown in the corner. */
  badge?: string
}) {
  const isHot =
    listing.velocity_class === 'spiking' || listing.velocity_class === 'explosive'

  return (
    <a
      href={listing.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition hover:border-primary-300 hover:shadow-md"
    >
      <div className="relative aspect-square w-full overflow-hidden bg-slate-50">
        {listing.thumbnail_url ? (
          // Use img instead of next/image since the remote host list varies
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={listing.thumbnail_url}
            alt={listing.title}
            className="h-full w-full object-cover transition group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-slate-400">
            no image
          </div>
        )}

        {badge && (
          <span className="absolute right-2 top-2 rounded-full bg-slate-900/80 px-2 py-0.5 text-xs font-semibold text-white">
            {badge}
          </span>
        )}
        {isHot && !badge && (
          <span className="absolute right-2 top-2 inline-flex items-center gap-1 rounded-full bg-rose-600 px-2 py-0.5 text-xs font-semibold text-white">
            <Zap className="h-3 w-3" aria-hidden /> hot
          </span>
        )}
      </div>

      <div className="p-3">
        <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium uppercase tracking-wide">
            {MARKETPLACE_LABELS[listing.marketplace]}
          </span>
          <span className={`rounded px-1.5 py-0.5 ${VELOCITY_STYLES[listing.velocity_class]}`}>
            {VELOCITY_LABELS[listing.velocity_class]}
          </span>
        </div>

        <h3 className="line-clamp-2 text-sm font-semibold text-slate-900">
          {listing.title}
        </h3>

        <div className="mt-2 flex items-center justify-between text-xs text-slate-600">
          <span className="font-medium text-slate-900">
            {listing.price_usd != null
              ? `$${listing.price_usd.toFixed(2)}`
              : '—'}
          </span>
          <span className="flex items-center gap-2">
            {listing.favorites != null && (
              <span className="inline-flex items-center gap-0.5">
                <Heart className="h-3 w-3" aria-hidden /> {compact(listing.favorites)}
              </span>
            )}
            {listing.reviews_count != null && (
              <span className="inline-flex items-center gap-0.5">
                <Star className="h-3 w-3" aria-hidden /> {compact(listing.reviews_count)}
              </span>
            )}
            {listing.est_daily_sales != null && (
              <span className="inline-flex items-center gap-0.5 text-rose-700">
                <TrendingUp className="h-3 w-3" aria-hidden />{' '}
                {listing.est_daily_sales.toFixed(1)}/d
              </span>
            )}
          </span>
        </div>

        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
          <span className="line-clamp-1">{listing.shop_handle ?? ''}</span>
          <ExternalLink className="h-3 w-3 text-slate-400" aria-hidden />
        </div>
      </div>
    </a>
  )
}

function compact(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}
