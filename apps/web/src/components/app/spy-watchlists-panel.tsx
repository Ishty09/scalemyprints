'use client'

import { Bell, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import type {
  AlertChannel,
  AlertItem,
  AlertListResponse,
  AlertTrigger,
  WatchlistCreateBody,
  WatchlistItem,
  WatchType,
} from '@scalemyprints/contracts'

import { apiClient, ApiClientError } from '@/lib/api-client'

const TRIGGERS: AlertTrigger[] = [
  'velocity_spike',
  'viral_hit',
  'new_listing',
  'price_drop',
  'price_increase',
  'saturation_drop',
]

const CHANNELS: AlertChannel[] = ['in_app', 'email', 'slack', 'webhook']

export function SpyWatchlistsPanel() {
  const [watchlists, setWatchlists] = useState<WatchlistItem[]>([])
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)

  async function refresh() {
    setLoading(true)
    try {
      const [w, a] = await Promise.all([
        apiClient.get<WatchlistItem[]>('/api/v1/spy/watchlists'),
        apiClient.get<AlertListResponse>('/api/v1/spy/alerts?limit=20'),
      ])
      setWatchlists(w)
      setAlerts(a.items)
      setUnread(a.unread_count)
    } catch (err) {
      if (err instanceof ApiClientError) {
        toast.error(err.message)
      } else {
        toast.error('Failed to load watchlists.')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
  }, [])

  async function deleteWatchlist(id: string) {
    try {
      await apiClient.delete(`/api/v1/spy/watchlists/${id}`)
      toast.success('Watchlist removed.')
      void refresh()
    } catch {
      toast.error('Could not delete watchlist.')
    }
  }

  return (
    <section className="space-y-6">
      <SpyWatchlistForm onCreated={refresh} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-2 flex items-center gap-2 font-display text-base font-bold text-slate-900">
            <Bell className="h-4 w-4 text-primary-600" aria-hidden /> Your watchlists
          </h3>
          {watchlists.length === 0 && !loading && (
            <p className="text-sm text-slate-500">
              No watchlists yet. Add one above to start receiving alerts.
            </p>
          )}
          <ul className="space-y-2">
            {watchlists.map((w) => (
              <li
                key={w.id}
                className="flex items-start justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-slate-900">
                    {w.label || w.target}
                  </div>
                  <div className="text-xs text-slate-500">
                    {w.watch_type} · {w.target}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {w.triggers.map((t) => (
                      <span
                        key={t}
                        className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700"
                      >
                        {t.replace('_', ' ')}
                      </span>
                    ))}
                    {w.channels.map((c) => (
                      <span
                        key={c.channel}
                        className="rounded bg-primary-50 px-1.5 py-0.5 text-xs text-primary-700"
                      >
                        {c.channel}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => void deleteWatchlist(w.id)}
                  className="ml-2 rounded p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                  aria-label="Delete watchlist"
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </article>

        <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="mb-2 flex items-center gap-2 font-display text-base font-bold text-slate-900">
            Recent alerts
            {unread > 0 && (
              <span className="rounded-full bg-rose-500 px-2 py-0.5 text-xs font-bold text-white">
                {unread}
              </span>
            )}
          </h3>
          {alerts.length === 0 && !loading && (
            <p className="text-sm text-slate-500">
              No alerts yet. Watchlists will populate this feed when they fire.
            </p>
          )}
          <ul className="space-y-2">
            {alerts.map((a) => (
              <li
                key={a.id}
                className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
              >
                <div className="flex items-center justify-between">
                  <strong className="text-slate-900">{a.headline}</strong>
                  <span
                    className={`text-xs ${
                      a.severity >= 75
                        ? 'text-rose-600'
                        : a.severity >= 50
                          ? 'text-amber-700'
                          : 'text-slate-500'
                    }`}
                  >
                    sev {a.severity}
                  </span>
                </div>
                {a.detail && <p className="mt-0.5 text-xs text-slate-600">{a.detail}</p>}
                <div className="mt-1 text-xs text-slate-400">
                  {new Date(a.created_at).toLocaleString()} · {a.trigger}
                </div>
              </li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  )
}

function SpyWatchlistForm({ onCreated }: { onCreated: () => void }) {
  const [watchType, setWatchType] = useState<WatchType>('phrase')
  const [target, setTarget] = useState('')
  const [label, setLabel] = useState('')
  const [triggers, setTriggers] = useState<AlertTrigger[]>([
    'velocity_spike',
    'viral_hit',
  ])
  const [channels, setChannels] = useState<AlertChannel[]>(['in_app'])
  const [webhookUrl, setWebhookUrl] = useState('')
  const [slackUrl, setSlackUrl] = useState('')
  const [email, setEmail] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!target.trim()) return
    const body: WatchlistCreateBody = {
      watch_type: watchType,
      target: target.trim(),
      label: label.trim() || null,
      triggers,
      channels: channels.map((channel) => ({
        channel,
        target:
          channel === 'webhook'
            ? webhookUrl
            : channel === 'slack'
              ? slackUrl
              : channel === 'email'
                ? email
                : null,
        enabled: true,
      })),
    }
    try {
      await apiClient.post<WatchlistItem, WatchlistCreateBody>(
        '/api/v1/spy/watchlists',
        body,
      )
      toast.success('Watchlist added.')
      setTarget('')
      setLabel('')
      onCreated()
    } catch (err) {
      const msg = err instanceof ApiClientError ? err.message : 'Failed.'
      toast.error(msg)
    }
  }

  function toggleTrigger(t: AlertTrigger) {
    setTriggers((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]))
  }

  function toggleChannel(c: AlertChannel) {
    setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]))
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <h3 className="flex items-center gap-2 font-display text-base font-bold text-slate-900">
        <Plus className="h-4 w-4 text-primary-600" aria-hidden /> Create watchlist
      </h3>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Type">
          <select
            value={watchType}
            onChange={(e) => setWatchType(e.target.value as WatchType)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          >
            <option value="phrase">Phrase</option>
            <option value="shop">Shop (marketplace:handle)</option>
            <option value="listing">Listing ID</option>
            <option value="viral_category">Viral category</option>
          </select>
        </Field>
        <Field label="Target">
          <input
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            placeholder={
              watchType === 'shop' ? 'etsy:ShopHandle' : 'vintage motorcycle'
            }
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>
        <Field label="Label (optional)">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="My niche"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>
      </div>

      <fieldset>
        <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Triggers
        </legend>
        <div className="mt-1 flex flex-wrap gap-2">
          {TRIGGERS.map((t) => (
            <label key={t} className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={triggers.includes(t)}
                onChange={() => toggleTrigger(t)}
              />
              {t.replace('_', ' ')}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Channels
        </legend>
        <div className="mt-1 flex flex-wrap gap-2">
          {CHANNELS.map((c) => (
            <label key={c} className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={channels.includes(c)}
                onChange={() => toggleChannel(c)}
              />
              {c}
            </label>
          ))}
        </div>
      </fieldset>

      {channels.includes('webhook') && (
        <Field label="Webhook URL">
          <input
            type="url"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://your-server/webhook"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>
      )}
      {channels.includes('slack') && (
        <Field label="Slack incoming webhook URL">
          <input
            type="url"
            value={slackUrl}
            onChange={(e) => setSlackUrl(e.target.value)}
            placeholder="https://hooks.slack.com/services/…"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>
      )}
      {channels.includes('email') && (
        <Field label="Email address">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>
      )}

      <button
        type="submit"
        disabled={!target.trim()}
        className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        Add watchlist
      </button>
    </form>
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
