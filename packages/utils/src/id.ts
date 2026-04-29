import { nanoid } from 'nanoid'

/**
 * ID generation utilities.
 * Uses nanoid for URL-safe, collision-resistant IDs.
 */

/**
 * Generic short ID (12 chars, URL-safe).
 * Use for non-critical IDs like cache keys, temporary refs.
 */
export function shortId(): string {
  return nanoid(12)
}

/**
 * Request ID for tracing API calls through logs/Sentry.
 * Prefix makes it recognizable in logs.
 */
export function requestId(): string {
  return `req_${nanoid(16)}`
}

/**
 * Correlation ID for tracking a logical operation across services.
 */
export function correlationId(): string {
  return `cor_${nanoid(16)}`
}
