'use client'

import { Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import {
  COUNTRY_LABELS,
  NICHE_COUNTRIES,
  type NicheCountry,
  type NicheSearchRequest,
} from '@scalemyprints/contracts'

interface NicheSearchFormProps {
  onSearch: (request: NicheSearchRequest) => void
  isLoading?: boolean
  initialKeyword?: string
  initialCountry?: NicheCountry
}

export function NicheSearchForm({
  onSearch,
  isLoading = false,
  initialKeyword = '',
  initialCountry = 'US',
}: NicheSearchFormProps) {
  const [keyword, setKeyword] = useState(initialKeyword)
  const [country, setCountry] = useState<NicheCountry>(initialCountry)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (keyword.trim().length < 2 || isLoading) return
    onSearch({ keyword: keyword.trim(), country })
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4">
        <label htmlFor="niche-keyword" className="mb-1.5 block text-sm font-medium text-slate-700">
          Niche keyword
        </label>
        <input
          id="niche-keyword"
          type="text"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="e.g. dog mom, plant lover, retro gaming..."
          required
          minLength={2}
          maxLength={80}
          className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
        />
        <p className="mt-1 text-xs text-slate-500">
          Try a phrase you&apos;d use in an Etsy search bar.
        </p>
      </div>

      <div className="mb-5">
        <label htmlFor="niche-country" className="mb-1.5 block text-sm font-medium text-slate-700">
          Target country
        </label>
        <div className="flex flex-wrap gap-2">
          {NICHE_COUNTRIES.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCountry(c)}
              aria-pressed={country === c}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                country === c
                  ? 'border-primary-500 bg-primary-50 text-primary-700'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300'
              }`}
            >
              {c} <span className="text-xs text-slate-400">{COUNTRY_LABELS[c]}</span>
            </button>
          ))}
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading || keyword.trim().length < 2}
        className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {isLoading ? (
          <>
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" aria-hidden="true" />
            Analyzing...
          </>
        ) : (
          <>
            <Search className="h-4 w-4" aria-hidden="true" />
            Analyze niche
          </>
        )}
      </button>
    </form>
  )
}
