'use client'

import {
  Activity,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronRight,
  DollarSign,
  ExternalLink,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
} from 'lucide-react'

import type {
  CompetitionLevel,
  NicheHealth,
  NicheRecord,
  TrendDirection,
} from '@scalemyprints/contracts'
import { COUNTRY_LABELS, EVENT_CATEGORY_LABELS } from '@scalemyprints/contracts'

interface NicheResultsProps {
  record: NicheRecord
}

const HEALTH_STYLES: Record<NicheHealth, { label: string; bg: string; text: string; ring: string }> = {
  hot: { label: 'Hot 🔥', bg: 'bg-emerald-50', text: 'text-emerald-700', ring: 'ring-emerald-200' },
  promising: { label: 'Promising', bg: 'bg-primary-50', text: 'text-primary-700', ring: 'ring-primary-200' },
  moderate: { label: 'Moderate', bg: 'bg-amber-50', text: 'text-amber-700', ring: 'ring-amber-200' },
  weak: { label: 'Weak', bg: 'bg-orange-50', text: 'text-orange-700', ring: 'ring-orange-200' },
  avoid: { label: 'Avoid', bg: 'bg-rose-50', text: 'text-rose-700', ring: 'ring-rose-200' },
}

const COMPETITION_LABELS: Record<CompetitionLevel, string> = {
  low: 'Low — wide open',
  medium: 'Medium — room to compete',
  high: 'High — crowded',
  saturated: 'Saturated — avoid',
}

export function NicheResults({ record }: NicheResultsProps) {
  const health = HEALTH_STYLES[record.health]

  return (
    <div className="space-y-5">
      {/* Top-line NHS card */}
      <div className={`rounded-2xl border-2 bg-white p-6 ring-4 ${health.ring}`}>
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              Niche Health Score
            </div>
            <h2 className="font-display text-2xl font-bold text-slate-900">
              &ldquo;{record.keyword}&rdquo; in {COUNTRY_LABELS[record.country]}
            </h2>
            <div className="mt-2 flex items-center gap-3">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${health.bg} ${health.text}`}>
                {health.label}
              </span>
              {record.degraded && (
                <span className="inline-flex items-center gap-1 text-xs text-amber-600">
                  <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                  Some data sources unavailable
                </span>
              )}
            </div>
          </div>

          <div className="text-center md:text-right">
            <div className="font-display text-5xl font-bold text-slate-900">{record.nhs_score}</div>
            <div className="mt-0.5 text-xs text-slate-500">out of 100</div>
          </div>
        </div>

        {/* NHS bar */}
        <div className="mt-5 h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all ${
              record.nhs_score >= 75
                ? 'bg-emerald-500'
                : record.nhs_score >= 55
                  ? 'bg-primary-500'
                  : record.nhs_score >= 40
                    ? 'bg-amber-500'
                    : 'bg-rose-500'
            }`}
            style={{ width: `${record.nhs_score}%` }}
          />
        </div>
      </div>

      {/* Sub-score grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        <SubScoreCard
          icon={<Users className="h-4 w-4 text-violet-600" aria-hidden="true" />}
          title="Demand"
          score={record.demand.score}
          subtitle={
            record.demand.listing_count != null
              ? `${record.demand.listing_count.toLocaleString()} listings · search index ${record.demand.search_volume_index}`
              : `Search index ${record.demand.search_volume_index}`
          }
        />

        <SubScoreCard
          icon={<TrendIcon direction={record.trend.direction} />}
          title="Trend"
          score={record.trend.score}
          subtitle={
            record.trend.growth_pct_90d != null
              ? `${record.trend.growth_pct_90d > 0 ? '+' : ''}${record.trend.growth_pct_90d}% over 90 days`
              : 'Insufficient data'
          }
        />

        <SubScoreCard
          icon={<Activity className="h-4 w-4 text-cyan-600" aria-hidden="true" />}
          title="Competition"
          score={record.competition.score}
          subtitle={COMPETITION_LABELS[record.competition.level]}
        />

        <SubScoreCard
          icon={<DollarSign className="h-4 w-4 text-emerald-600" aria-hidden="true" />}
          title="Profitability"
          score={record.profitability.score}
          subtitle={
            record.profitability.estimated_margin_usd != null
              ? `Est. margin ~$${record.profitability.estimated_margin_usd.toFixed(2)}/sale`
              : 'No price data'
          }
        />

        <SubScoreCard
          icon={<Calendar className="h-4 w-4 text-amber-600" aria-hidden="true" />}
          title="Seasonality"
          score={record.seasonality.score}
          subtitle={
            record.seasonality.nearest_event_name && record.seasonality.days_until_event != null
              ? `${record.seasonality.nearest_event_name} in ${record.seasonality.days_until_event} days`
              : 'No major event ahead'
          }
        />
      </div>

      {/* Upcoming events */}
      {record.upcoming_events.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="mb-4 flex items-center gap-2 font-display text-lg font-semibold text-slate-900">
            <Calendar className="h-5 w-5 text-primary-600" aria-hidden="true" />
            Upcoming events to design for
          </h3>
          <ul className="space-y-3">
            {record.upcoming_events.map((event) => (
              <li
                key={event.id}
                className="flex items-start gap-3 rounded-lg border border-slate-100 bg-slate-50/50 p-3"
              >
                <div className="flex-shrink-0 rounded-md bg-white px-2 py-1 text-center text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                  <div className="text-slate-500">
                    {new Date(event.event_date).toLocaleDateString('en-US', {
                      month: 'short',
                    })}
                  </div>
                  <div className="text-base font-bold text-slate-900">
                    {new Date(event.event_date).getDate()}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="font-medium text-slate-900">{event.name}</div>
                  <div className="mt-0.5 text-xs text-slate-500">
                    {EVENT_CATEGORY_LABELS[event.category]} · POD relevance {event.pod_relevance_score}/100
                  </div>
                  {event.suggested_niches.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {event.suggested_niches.slice(0, 5).map((niche) => (
                        <span
                          key={niche}
                          className="rounded-md bg-white px-2 py-0.5 text-xs text-slate-600 ring-1 ring-slate-200"
                        >
                          {niche}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Related keywords */}
      {record.related_keywords.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="mb-3 font-display text-lg font-semibold text-slate-900">
            Related searches
          </h3>
          <div className="flex flex-wrap gap-2">
            {record.related_keywords.map((kw) => (
              <span
                key={kw}
                className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
              >
                {kw}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Sample listings */}
      {record.sample_listings_urls.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-6">
          <h3 className="mb-3 font-display text-lg font-semibold text-slate-900">
            Sample listings (top sellers)
          </h3>
          <ul className="space-y-2">
            {record.sample_listings_urls.map((url) => (
              <li key={url}>
                <a
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm text-primary-600 hover:underline"
                >
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  {decodeURIComponent(url.split('/').pop() ?? url).replace(/-/g, ' ')}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Footer meta */}
      <div className="text-xs text-slate-400">
        Analyzed in {record.duration_ms}ms · sources:{' '}
        {record.data_sources_used.join(', ')}
      </div>
    </div>
  )
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

interface SubScoreCardProps {
  icon: React.ReactNode
  title: string
  score: number
  subtitle: string
}

function SubScoreCard({ icon, title, score, subtitle }: SubScoreCardProps) {
  const barColor =
    score >= 75
      ? 'bg-emerald-500'
      : score >= 55
        ? 'bg-primary-500'
        : score >= 40
          ? 'bg-amber-500'
          : 'bg-rose-400'

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-sm font-medium text-slate-700">{title}</span>
        </div>
        <span className="font-display text-xl font-bold text-slate-900">{score}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${barColor} transition-all`}
          style={{ width: `${score}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-slate-500">{subtitle}</p>
    </div>
  )
}

function TrendIcon({ direction }: { direction: TrendDirection }) {
  if (direction === 'rising') return <TrendingUp className="h-4 w-4 text-emerald-600" aria-hidden="true" />
  if (direction === 'declining') return <TrendingDown className="h-4 w-4 text-rose-500" aria-hidden="true" />
  return <ChevronRight className="h-4 w-4 text-slate-400" aria-hidden="true" />
}

// Re-exported for unused import suppression
export { CheckCircle2 }
