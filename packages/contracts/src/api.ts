import { z } from 'zod'

/**
 * API response envelope.
 *
 * Every API response (from /api routes and from workers) follows this shape.
 * This gives the frontend a single, predictable contract for success/error
 * handling and enables middleware to process responses uniformly.
 */

// ---------------------------------------------------------------------------
// Error codes — stable strings that clients can switch on
// ---------------------------------------------------------------------------

export const ERROR_CODES = {
  // Auth & access
  UNAUTHORIZED: 'unauthorized',
  FORBIDDEN: 'forbidden',
  SESSION_EXPIRED: 'session_expired',

  // Validation
  VALIDATION_ERROR: 'validation_error',
  INVALID_INPUT: 'invalid_input',

  // Resource
  NOT_FOUND: 'not_found',
  ALREADY_EXISTS: 'already_exists',
  CONFLICT: 'conflict',

  // Limits & quotas
  QUOTA_EXCEEDED: 'quota_exceeded',
  RATE_LIMITED: 'rate_limited',
  PLAN_REQUIRED: 'plan_required',

  // External services
  EXTERNAL_SERVICE_ERROR: 'external_service_error',
  EXTERNAL_SERVICE_TIMEOUT: 'external_service_timeout',

  // Server
  INTERNAL_ERROR: 'internal_error',
  SERVICE_UNAVAILABLE: 'service_unavailable',

  // Business
  FEATURE_DISABLED: 'feature_disabled',
  ACCOUNT_SUSPENDED: 'account_suspended',
} as const

export type ErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES]

// ---------------------------------------------------------------------------
// Error detail schema
// ---------------------------------------------------------------------------

export const API_ERROR_SCHEMA = z.object({
  code: z.string(),
  message: z.string(),
  details: z.record(z.unknown()).optional(),
  request_id: z.string().optional(),
})
export type ApiError = z.infer<typeof API_ERROR_SCHEMA>

// ---------------------------------------------------------------------------
// Discriminated union envelope — TS narrows type based on `ok` field
// ---------------------------------------------------------------------------

export interface ApiSuccess<T> {
  readonly ok: true
  readonly data: T
  readonly meta?: ApiMeta
}

export interface ApiFailure {
  readonly ok: false
  readonly error: ApiError
}

export type ApiResponse<T> = ApiSuccess<T> | ApiFailure

// ---------------------------------------------------------------------------
// Metadata — pagination, timing, etc.
// ---------------------------------------------------------------------------

export interface ApiMeta {
  readonly request_id?: string
  readonly duration_ms?: number
  readonly pagination?: PaginationMeta
  readonly cached?: boolean
  readonly cache_age_seconds?: number
}

export interface PaginationMeta {
  readonly page: number
  readonly per_page: number
  readonly total: number
  readonly total_pages: number
  readonly has_next: boolean
  readonly has_prev: boolean
}

// ---------------------------------------------------------------------------
// Helpers — for both frontend consumers and backend builders
// ---------------------------------------------------------------------------

export function isApiSuccess<T>(response: ApiResponse<T>): response is ApiSuccess<T> {
  return response.ok === true
}

export function isApiFailure<T>(response: ApiResponse<T>): response is ApiFailure {
  return response.ok === false
}

export function buildSuccess<T>(data: T, meta?: ApiMeta): ApiSuccess<T> {
  return { ok: true, data, ...(meta ? { meta } : {}) }
}

export function buildFailure(
  code: ErrorCode | string,
  message: string,
  details?: Record<string, unknown>,
  requestId?: string,
): ApiFailure {
  return {
    ok: false,
    error: {
      code,
      message,
      ...(details ? { details } : {}),
      ...(requestId ? { request_id: requestId } : {}),
    },
  }
}
