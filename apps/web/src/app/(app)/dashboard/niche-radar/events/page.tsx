'use client'

import { ArrowLeft, Calendar, Sparkles } from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'

import {
  COUNTRY_LABELS,
  EVENT_CATEGORY_LABELS,
  NICHE_COUNTRIES,
  type EventCategory,
  type EventListItem,
  type NicheCountry,
} from '@scalemyprints/contracts'

import { useNicheEvents } from '@/hooks/use-niche'

const CATEGORY_FILTERS: ReadonlyArray<{ value: EventCategory | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'holiday', label: 'Holidays' },
  { value: 'cultural', label: 'Cultural' },
  { value: 'religious', label: 'Religious' },
  { value: 'sports', label: 'Sports' },
  { value: 'awareness', label: 'Awareness' },
  { value: 'seasonal', label: 'Seasonal' },
  { value: 'school', label: 'School' },
  { value: 'quirky', label: 'Quirky' },
]

const RANGE_OPTIONS = [
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 180, label: '6 months' },
  { value: 365, label: '12 months' },
] as const

export default function NicheEventsPage() {
  const [country, setCountry] = useState<NicheCountry>('US')
  const [days, setDays] = useState<number>(90)
  const [category, setCategory] = useState<EventCategory | 'all'>('all')

  const today = new Date().toISOString().slice(0, 10)
  const toDate = new Date(Date.now() + days * 86400 * 1000).toISOString().slice(0, 10)

  const { data: events, isLoading } = useNicheEvents({
    country,
    from: today,
    to: toDate,
    category: category === 'all' ? undefined : category,
  })

  const groupedByDate = groupEventsByDate(events ?? [])

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        href="/dashboard/niche-radar"
        className="mb-4 inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to Niche Radar
      </Link>

      <header className="mb-6">
        <div className="mb-2 flex items-center gap-3">
          <Calendar className="h-7 w-7 text-primary-600" aria-hidden="true" />
          <h1 className="font-display text-3xl font-bold text-slate-900">Upcoming events</h1>
        </div>
        <p className="text-slate-600">
          POD-relevant holidays, cultural events, and seasonal moments. Plan designs ahead.
        </p>
      </header>

      {/* Filters */}
      <div className="mb-6 space-y-4 rounded-xl border border-slate-200 bg-white p-5">
        <div>
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Country
          </label>
          <div className="flex flex-wrap gap-2">
            {NICHE_COUNTRIES.map((c) => (
              <button
                key={c}
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

        <div>
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Time window
          </label>
          <div className="flex flex-wrap gap-2">
            {RANGE_OPTIONS.map((r) => (
              <button
                key={r.value}
                onClick={() => setDays(r.value)}
                aria-pressed={days === r.value}
                className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                  days === r.value
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-slate-200 text-slate-600 hover:border-slate-300'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Category
          </label>
          <div className="flex flex-wrap gap-2">
            {CATEGORY_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setCategory(f.value)}
                aria-pressed={category === f.value}
                className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                  category === f.value
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-slate-200 text-slate-600 hover:border-slate-300'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-primary-200 border-t-primary-600" />
          Loading events...
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (events?.length ?? 0) === 0 && (
        <div className="rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center text-slate-500">
          No events in this window. Try a wider range or different category.
        </div>
      )}

      {/* Day-by-day grouped events */}
      {!isLoading && events && events.length > 0 && (
        <div className="space-y-6">
          {groupedByDate.map(({ groupLabel, items }) => (
            <section key={groupLabel}>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
                {groupLabel}
              </h2>
              <ul className="space-y-3">
                {items.map((event) => (
                  <EventCard key={event.id} event={event} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

// -----------------------------------------------------------------------------

function EventCard({ event }: { event: EventListItem }) {
  const date = new Date(event.event_date)
  const relevanceColor =
    event.pod_relevance_score >= 80
      ? 'bg-emerald-500'
      : event.pod_relevance_score >= 60
        ? 'bg-primary-500'
        : event.pod_relevance_score >= 40
          ? 'bg-amber-500'
          : 'bg-slate-300'

  const daysLabel =
    event.days_until === 0
      ? 'Today'
      : event.days_until === 1
        ? 'Tomorrow'
        : `In ${event.days_until} days`

  return (
    <li className="flex items-start gap-4 rounded-xl border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md">
      <div className="flex-shrink-0 rounded-lg bg-slate-50 px-3 py-2 text-center ring-1 ring-slate-200">
        <div className="text-xs font-semibold uppercase text-slate-500">
          {date.toLocaleDateString('en-US', { month: 'short' })}
        </div>
        <div className="font-display text-2xl font-bold text-slate-900">
          {date.getDate()}
        </div>
        <div className="text-xs text-slate-400">
          {date.toLocaleDateString('en-US', { weekday: 'short' })}
        </div>
      </div>

      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-slate-900">{event.name}</h3>
          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {EVENT_CATEGORY_LABELS[event.category]}
          </span>
        </div>

        <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
          <span>{daysLabel}</span>
          <span>·</span>
          <span className="flex items-center gap-1.5">
            <span className={`inline-block h-1.5 w-12 rounded-full ${relevanceColor}`} />
            POD relevance {event.pod_relevance_score}/100
          </span>
        </div>

        {event.suggested_niches.length > 0 && (
          <div className="mt-3">
            <div className="mb-1.5 inline-flex items-center gap-1 text-xs font-medium text-slate-600">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              Niche ideas:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {event.suggested_niches.slice(0, 6).map((niche) => (
                <Link
                  key={niche}
                  href={`/dashboard/niche-radar?keyword=${encodeURIComponent(niche)}&country=${event.country}`}
                  className="rounded-md bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700 hover:bg-primary-100"
                >
                  {niche}
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </li>
  )
}

// -----------------------------------------------------------------------------
// Grouping helper — chunks events into "This week", "Next week", "Later"
// -----------------------------------------------------------------------------

interface EventGroup {
  groupLabel: string
  items: EventListItem[]
}

function groupEventsByDate(events: EventListItem[]): EventGroup[] {
  const groups: Record<string, EventListItem[]> = {
    'This week': [],
    'Next week': [],
    'This month': [],
    Later: [],
  }
  for (const e of events) {
    if (e.days_until <= 7) groups['This week']!.push(e)
    else if (e.days_until <= 14) groups['Next week']!.push(e)
    else if (e.days_until <= 31) groups['This month']!.push(e)
    else groups['Later']!.push(e)
  }
  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([groupLabel, items]) => ({ groupLabel, items }))
}
