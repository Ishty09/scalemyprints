'use client'

import { Brain, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import type {
  NicheSuggesterBody,
  NicheSuggesterResponse,
} from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

export function SpyNicheSuggesterPanel() {
  const [data, setData] = useState<NicheSuggesterResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [minReadiness, setMinReadiness] = useState(55)
  const [maxRisk, setMaxRisk] = useState(60)
  const [styles, setStyles] = useState('minimal, vintage')
  const [excluded, setExcluded] = useState('')

  async function run() {
    setLoading(true)
    const body: NicheSuggesterBody = {
      preferred_styles: styles
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      excluded_phrases: excluded
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      min_pod_readiness: minReadiness,
      max_risk: maxRisk,
      limit: 10,
    }
    try {
      const r = await apiClient.post<NicheSuggesterResponse, NicheSuggesterBody>(
        '/api/v1/spy/niche-suggester',
        body,
      )
      setData(r)
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : 'Failed.'
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <header className="mb-3 flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary-600" aria-hidden />
          <h2 className="font-display text-lg font-bold text-slate-900">
            AI niche suggester
          </h2>
        </header>
        <p className="mb-3 text-sm text-slate-600">
          Cross-source ranker combining hot movers + viral mining, filtered
          against trademark risk. Tell it the styles you can produce and the
          risk you tolerate.
        </p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Preferred styles (comma-separated)">
            <input
              type="text"
              value={styles}
              onChange={(e) => setStyles(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label="Exclude phrases (comma-separated)">
            <input
              type="text"
              value={excluded}
              onChange={(e) => setExcluded(e.target.value)}
              placeholder="politics, trademark phrases…"
              className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
            />
          </Field>
          <Field label={`Min POD-readiness: ${minReadiness}`}>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minReadiness}
              onChange={(e) => setMinReadiness(Number(e.target.value))}
              className="w-full"
            />
          </Field>
          <Field label={`Max trademark risk: ${maxRisk}`}>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={maxRisk}
              onChange={(e) => setMaxRisk(Number(e.target.value))}
              className="w-full"
            />
          </Field>
        </div>

        <button
          type="button"
          onClick={run}
          disabled={loading}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          Suggest my next 10
        </button>
      </div>

      {data && data.suggestions.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
          No suggestions matched your filters. Loosen min readiness or raise max
          risk.
        </div>
      )}

      {data && data.suggestions.length > 0 && (
        <ol className="space-y-2">
          {data.suggestions.map((s, idx) => (
            <li
              key={`${s.source}-${s.phrase}`}
              className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-400">
                      #{idx + 1}
                    </span>
                    <strong className="text-sm text-slate-900">{s.phrase}</strong>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                      {s.source.replace('_', ' ')}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-slate-600">{s.rationale}</p>
                  <div className="mt-1 flex flex-wrap gap-1 text-xs">
                    {s.suggested_styles.map((style) => (
                      <span
                        key={style}
                        className="rounded bg-primary-50 px-1.5 py-0.5 text-primary-700"
                      >
                        {style.replace('_', ' ')}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex-shrink-0 text-right text-xs">
                  <div className="text-emerald-700">opp {s.opportunity_score}</div>
                  <div className="text-rose-600">risk {s.risk_score}</div>
                  <div className="text-slate-500">sat {s.saturation_score}</div>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
    </label>
  )
}
