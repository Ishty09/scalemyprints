/**
 * Typed wrapper around chrome.storage.local.
 *
 * Keys are namespaced under `smp:` so we don't collide with other extensions
 * that share the storage area.
 */

import type { TrademarkSearchResponse } from '@scalemyprints/contracts'

import type { UsageStats } from './messages'

const PREFIX = 'smp:'
const KEYS = {
  usageStats: `${PREFIX}usage_stats`,
  resultCache: (key: string) => `${PREFIX}cache:${key}`,
} as const

const DEFAULT_USAGE: UsageStats = {
  searches_today: 0,
  searches_total: 0,
  last_search_at: null,
}

export async function getUsageStats(): Promise<UsageStats> {
  const result = await chrome.storage.local.get(KEYS.usageStats)
  const stored = result[KEYS.usageStats] as UsageStats | undefined
  if (!stored) return { ...DEFAULT_USAGE }

  // Reset daily counter if last search was on a different day
  if (stored.last_search_at) {
    const lastDay = new Date(stored.last_search_at).toDateString()
    const today = new Date().toDateString()
    if (lastDay !== today) {
      return { ...stored, searches_today: 0 }
    }
  }
  return stored
}

export async function recordSearch(): Promise<UsageStats> {
  const current = await getUsageStats()
  const next: UsageStats = {
    searches_today: current.searches_today + 1,
    searches_total: current.searches_total + 1,
    last_search_at: new Date().toISOString(),
  }
  await chrome.storage.local.set({ [KEYS.usageStats]: next })
  return next
}

interface CachedResult {
  response: TrademarkSearchResponse
  cached_at: number
}

export async function getCachedResult(
  cacheKey: string,
  maxAgeMinutes: number,
): Promise<TrademarkSearchResponse | null> {
  const storageKey = KEYS.resultCache(cacheKey)
  const result = await chrome.storage.local.get(storageKey)
  const entry = result[storageKey] as CachedResult | undefined
  if (!entry) return null

  const ageMinutes = (Date.now() - entry.cached_at) / 60_000
  if (ageMinutes > maxAgeMinutes) {
    await chrome.storage.local.remove(storageKey)
    return null
  }
  return entry.response
}

export async function setCachedResult(
  cacheKey: string,
  response: TrademarkSearchResponse,
): Promise<void> {
  const storageKey = KEYS.resultCache(cacheKey)
  const entry: CachedResult = {
    response,
    cached_at: Date.now(),
  }
  await chrome.storage.local.set({ [storageKey]: entry })
}

export function buildCacheKey(phrase: string, jurisdictions: string[]): string {
  const normalized = phrase.trim().toLowerCase().replace(/\s+/g, ' ')
  const jur = [...jurisdictions].sort().join(',')
  return `${normalized}|${jur}`
}
