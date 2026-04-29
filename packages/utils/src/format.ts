/**
 * Formatting utilities — consistent display across the app.
 */

/**
 * Format a number as USD currency.
 */
export function formatCurrency(
  amount: number,
  options: { showCents?: boolean; currency?: string } = {},
): string {
  const { showCents = false, currency = 'USD' } = options
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: showCents ? 2 : 0,
    maximumFractionDigits: showCents ? 2 : 0,
  }).format(amount)
}

/**
 * Format a number with thousands separators.
 */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

/**
 * Format a percentage (input: 0-1 or 0-100 depending on isDecimal).
 */
export function formatPercent(value: number, options: { isDecimal?: boolean } = {}): string {
  const normalized = options.isDecimal ? value * 100 : value
  return `${Math.round(normalized)}%`
}

/**
 * Format an ISO date string as a human-readable date.
 */
export function formatDate(
  dateIso: string,
  style: 'short' | 'medium' | 'long' | 'full' = 'medium',
): string {
  const date = new Date(dateIso)
  return new Intl.DateTimeFormat('en-US', { dateStyle: style }).format(date)
}

/**
 * Format "time ago" relative to now.
 */
export function formatRelativeTime(dateIso: string): string {
  const date = new Date(dateIso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)

  if (diffSec < 60) return 'just now'
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`
  if (diffSec < 2592000) return `${Math.floor(diffSec / 604800)}w ago`
  if (diffSec < 31536000) return `${Math.floor(diffSec / 2592000)}mo ago`
  return `${Math.floor(diffSec / 31536000)}y ago`
}

/**
 * Format a duration in ms as human-readable.
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`
  const hours = Math.floor(ms / 3_600_000)
  const mins = Math.floor((ms % 3_600_000) / 60_000)
  return `${hours}h ${mins}m`
}

/**
 * Truncate a string at a max length with ellipsis.
 */
export function truncate(text: string, maxLength: number, suffix = '…'): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - suffix.length).trimEnd() + suffix
}

/**
 * Slugify a string (URL-safe).
 */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
}
