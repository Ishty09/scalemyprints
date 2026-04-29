/**
 * Typed API client.
 *
 * Wraps fetch() with:
 * - Typed request/response bodies
 * - Automatic envelope unwrapping (ApiResponse → T or throw ApiClientError)
 * - Supabase session token attached to Authorization header
 * - Request ID forwarding from the browser
 *
 * Usage:
 *   const result = await apiClient.post<TrademarkSearchResponse, TrademarkSearchRequest>(
 *     '/api/v1/trademark/search',
 *     { phrase: 'dog mom', ... }
 *   )
 */

import type { ApiError } from '@scalemyprints/contracts'

import { env } from '@/lib/env'
import { createSupabaseBrowserClient } from '@/lib/supabase/client'

const DEFAULT_TIMEOUT_MS = 30_000

export class ApiClientError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown> | undefined
  readonly requestId: string | undefined

  constructor(code: string, message: string, status: number, options?: {
    details?: Record<string, unknown>
    requestId?: string
  }) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.status = status
    this.details = options?.details
    this.requestId = options?.requestId
  }
}

type FetchOptions = {
  headers?: HeadersInit
  signal?: AbortSignal
  /** Attach Supabase access token if available. Default: true */
  auth?: boolean
}

async function getAuthToken(): Promise<string | null> {
  try {
    const supabase = createSupabaseBrowserClient()
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  } catch {
    return null
  }
}

function generateRequestId(): string {
  return `req_${Math.random().toString(36).slice(2, 18)}`
}

async function request<TResponse>(
  method: string,
  path: string,
  body: unknown,
  options: FetchOptions = {},
): Promise<TResponse> {
  const url = path.startsWith('http') ? path : `${env.NEXT_PUBLIC_API_URL}${path}`

  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  headers.set('Accept', 'application/json')
  headers.set('X-Request-ID', generateRequestId())

  if (options.auth !== false) {
    const token = await getAuthToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS)
  // Merge caller signal with our timeout
  options.signal?.addEventListener('abort', () => controller.abort())

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      credentials: 'omit',
    })
  } catch (err) {
    clearTimeout(timeoutId)
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new ApiClientError('request_timeout', 'Request timed out', 0)
    }
    throw new ApiClientError(
      'network_error',
      err instanceof Error ? err.message : 'Network error',
      0,
    )
  }
  clearTimeout(timeoutId)

  // Parse JSON — tolerate non-JSON by treating as opaque failure
  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new ApiClientError(
      'invalid_response',
      'Server returned non-JSON response',
      response.status,
    )
  }

  // Handle envelope
  if (isFailureEnvelope(payload)) {
    throw new ApiClientError(payload.error.code, payload.error.message, response.status, {
      details: payload.error.details,
      requestId: payload.error.request_id,
    })
  }

  if (isSuccessEnvelope<TResponse>(payload)) {
    return payload.data
  }

  // Anything else is a protocol violation — treat as 500
  throw new ApiClientError(
    'malformed_response',
    'Server returned unexpected payload',
    response.status,
  )
}

// -----------------------------------------------------------------------------
// Envelope type guards
// -----------------------------------------------------------------------------

function isSuccessEnvelope<T>(payload: unknown): payload is { ok: true; data: T } {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    (payload as { ok?: unknown }).ok === true &&
    'data' in payload
  )
}

function isFailureEnvelope(payload: unknown): payload is { ok: false; error: ApiError } {
  return (
    typeof payload === 'object' &&
    payload !== null &&
    (payload as { ok?: unknown }).ok === false &&
    'error' in payload
  )
}

// -----------------------------------------------------------------------------
// Public API
// -----------------------------------------------------------------------------

export const apiClient = {
  get<TResponse>(path: string, options?: FetchOptions): Promise<TResponse> {
    return request<TResponse>('GET', path, undefined, options)
  },
  post<TResponse, TBody = unknown>(
    path: string,
    body?: TBody,
    options?: FetchOptions,
  ): Promise<TResponse> {
    return request<TResponse>('POST', path, body, options)
  },
  put<TResponse, TBody = unknown>(
    path: string,
    body?: TBody,
    options?: FetchOptions,
  ): Promise<TResponse> {
    return request<TResponse>('PUT', path, body, options)
  },
  delete<TResponse>(path: string, options?: FetchOptions): Promise<TResponse> {
    return request<TResponse>('DELETE', path, undefined, options)
  },
}
