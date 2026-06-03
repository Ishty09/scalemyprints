'use client'

import { Flame, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'

import type { ViralFeedResponse } from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

export function SpyViralFeed() {
  const [data, setData] = useState<ViralFeedResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [minReadiness, setMinReadiness] = useState(50)

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      const result = await apiClient.get<ViralFeedResponse>(
        `/api/v1/spy/viral-feed?min_pod_readiness=${minReadiness}&limit=40`,
      )
      setData(result)
    } catch (err) {
      const msg =
        err instanceof ApiClientError ? err.message : 'Failed to load viral feed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <header className="mb-3 flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-primary-600" aria-hidden />
          <h2 className="font-display text-lg font-bold text-slate-900">
            Viral feed
          </h2>
          <span className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            Reddit · TikTok · X
          </span>
        </header>

        <p className="mb-3 text-sm text-slate-600">
          Trending phrases mined right now from social sources, scored
          for POD readiness by an LLM. Filter by minimum readiness to
          cut the noise.
        </p>

        <div className="flex items-end gap-3">
          <label className="flex-1">
            <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Min readiness: {minReadiness}
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={minReadiness}
              onChange={(e) => setMinReadiness(Number(e.target.value))}
              className="w-full"
            />
          </label>
          <button
            type="button"
            onClick={refresh}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            Refresh feed
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {error}
        </div>
      )}

      {data && data.signals.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
          Nothing above the threshold. Try lowering &quot;min readiness&quot;.
        </div>
      )}

      {data && data.signals.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-slate-500">
            {data.signals.length} signals · {data.sources_used.join(', ') || 'no source'}{' '}
            · {data.duration_ms} ms
            {data.sources_failed.length > 0 && (
              <span className="ml-2 text-rose-600">
                · failed: {data.sources_failed.map((f) => f.source).join(', ')}
              </span>
            )}
          </div>
          <ul className="space-y-2">
            {data.signals.map((s) => (
              <li
                key={`${s.source}-${s.phrase}`}
                className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm"
              >
                <div className="flex-shrink-0">
                  <ScoreBubble score={s.pod_readiness_score} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <strong className="truncate text-sm text-slate-900">
                      {s.phrase}
                    </strong>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs uppercase text-slate-600">
                      {s.source}
                    </span>
                    <span className="inline-flex items-center gap-0.5 text-xs text-slate-500">
                      <Flame className="h-3 w-3" aria-hidden /> {s.momentum_score}
                    </span>
                  </div>
                  {s.note && (
                    <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">
                      {s.note}
                    </p>
                  )}
                  {s.suggested_styles.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {s.suggested_styles.slice(0, 4).map((style) => (
                        <span
                          key={style}
                          className="rounded bg-primary-50 px-1.5 py-0.5 text-xs text-primary-700"
                        >
                          {style.replace('_', ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {s.source_url && (
                  <a
                    href={s.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 text-xs font-semibold text-primary-700 hover:underline"
                  >
                    Source ↗
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function ScoreBubble({ score }: { score: number }) {
  const color =
    score >= 80
      ? 'bg-emerald-100 text-emerald-700'
      : score >= 60
        ? 'bg-amber-100 text-amber-700'
        : 'bg-slate-100 text-slate-600'
  return (
    <div
      className={`flex h-12 w-12 items-center justify-center rounded-full font-bold ${color}`}
    >
      {score}
    </div>
  )
}
