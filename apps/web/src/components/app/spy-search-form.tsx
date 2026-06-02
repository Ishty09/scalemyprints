'use client'

import { Loader2, Search } from 'lucide-react'
import { useState } from 'react'

import type { Marketplace, SpySearchBody } from '@scalemyprints/contracts'
import { MARKETPLACES, MARKETPLACE_LABELS } from '@scalemyprints/contracts'

export function SpySearchForm({
  onSubmit,
  isLoading,
}: {
  onSubmit: (body: SpySearchBody) => void
  isLoading: boolean
}) {
  const [text, setText] = useState('')
  const [selected, setSelected] = useState<Marketplace[]>([
    'etsy',
    'amazon_merch',
    'redbubble',
  ])

  function toggle(mkt: Marketplace) {
    setSelected((prev) =>
      prev.includes(mkt) ? prev.filter((m) => m !== mkt) : [...prev, mkt],
    )
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = text.trim()
    if (!trimmed) return
    const isUrl = /^https?:\/\//i.test(trimmed)
    onSubmit({
      text: isUrl ? null : trimmed,
      listing_url: isUrl ? trimmed : null,
      marketplaces: selected,
      limit: 24,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <label htmlFor="spy-query" className="block text-sm font-semibold text-slate-700">
        Search across marketplaces
      </label>
      <div className="flex gap-2">
        <input
          id="spy-query"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="vintage motorcycle, or paste a listing URL"
          disabled={isLoading}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 disabled:bg-slate-50"
        />
        <button
          type="submit"
          disabled={isLoading || !text.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Search className="h-4 w-4" aria-hidden />
          )}
          {isLoading ? 'Scanning' : 'Spy'}
        </button>
      </div>

      <fieldset className="space-y-1">
        <legend className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Marketplaces
        </legend>
        <div className="flex flex-wrap gap-2">
          {MARKETPLACES.map((mkt) => {
            const active = selected.includes(mkt)
            const supported = ['etsy', 'amazon_merch', 'redbubble'].includes(mkt)
            return (
              <button
                key={mkt}
                type="button"
                onClick={() => supported && toggle(mkt)}
                disabled={!supported}
                title={supported ? '' : 'Coming in Phase 2'}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
                  !supported
                    ? 'cursor-not-allowed border-dashed border-slate-200 text-slate-400'
                    : active
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400'
                }`}
              >
                {MARKETPLACE_LABELS[mkt]}
              </button>
            )
          })}
        </div>
      </fieldset>
    </form>
  )
}
