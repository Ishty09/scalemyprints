import { ERROR_CODES, type ErrorCode } from './api'

/**
 * Typed error classes.
 *
 * Throw these in app/worker code; they can be caught and translated to
 * ApiFailure responses with the right HTTP status codes.
 */

// HTTP status codes mapped to error codes
export const ERROR_STATUS_MAP: Record<ErrorCode, number> = {
  [ERROR_CODES.UNAUTHORIZED]: 401,
  [ERROR_CODES.FORBIDDEN]: 403,
  [ERROR_CODES.SESSION_EXPIRED]: 401,
  [ERROR_CODES.VALIDATION_ERROR]: 400,
  [ERROR_CODES.INVALID_INPUT]: 400,
  [ERROR_CODES.NOT_FOUND]: 404,
  [ERROR_CODES.ALREADY_EXISTS]: 409,
  [ERROR_CODES.CONFLICT]: 409,
  [ERROR_CODES.QUOTA_EXCEEDED]: 402, // Payment Required (signals upgrade)
  [ERROR_CODES.RATE_LIMITED]: 429,
  [ERROR_CODES.PLAN_REQUIRED]: 402,
  [ERROR_CODES.EXTERNAL_SERVICE_ERROR]: 502,
  [ERROR_CODES.EXTERNAL_SERVICE_TIMEOUT]: 504,
  [ERROR_CODES.INTERNAL_ERROR]: 500,
  [ERROR_CODES.SERVICE_UNAVAILABLE]: 503,
  [ERROR_CODES.FEATURE_DISABLED]: 403,
  [ERROR_CODES.ACCOUNT_SUSPENDED]: 403,
}

export class AppError extends Error {
  readonly code: ErrorCode
  readonly details?: Record<string, unknown>
  readonly httpStatus: number

  constructor(code: ErrorCode, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'AppError'
    this.code = code
    this.details = details
    this.httpStatus = ERROR_STATUS_MAP[code] ?? 500
    Object.setPrototypeOf(this, AppError.prototype)
  }
}

export class UnauthorizedError extends AppError {
  constructor(message = 'Authentication required') {
    super(ERROR_CODES.UNAUTHORIZED, message)
    this.name = 'UnauthorizedError'
    Object.setPrototypeOf(this, UnauthorizedError.prototype)
  }
}

export class ForbiddenError extends AppError {
  constructor(message = 'Access denied') {
    super(ERROR_CODES.FORBIDDEN, message)
    this.name = 'ForbiddenError'
    Object.setPrototypeOf(this, ForbiddenError.prototype)
  }
}

export class ValidationError extends AppError {
  constructor(message: string, details?: Record<string, unknown>) {
    super(ERROR_CODES.VALIDATION_ERROR, message, details)
    this.name = 'ValidationError'
    Object.setPrototypeOf(this, ValidationError.prototype)
  }
}

export class NotFoundError extends AppError {
  constructor(resource: string) {
    super(ERROR_CODES.NOT_FOUND, `${resource} not found`)
    this.name = 'NotFoundError'
    Object.setPrototypeOf(this, NotFoundError.prototype)
  }
}

export class QuotaExceededError extends AppError {
  constructor(tool: string, limit: string) {
    super(ERROR_CODES.QUOTA_EXCEEDED, `Quota exceeded for ${tool} (${limit}). Upgrade to continue.`, {
      tool,
      limit,
    })
    this.name = 'QuotaExceededError'
    Object.setPrototypeOf(this, QuotaExceededError.prototype)
  }
}

export class RateLimitedError extends AppError {
  constructor(retryAfterSeconds?: number) {
    super(ERROR_CODES.RATE_LIMITED, 'Too many requests. Please slow down.', {
      retry_after_seconds: retryAfterSeconds,
    })
    this.name = 'RateLimitedError'
    Object.setPrototypeOf(this, RateLimitedError.prototype)
  }
}

export class ExternalServiceError extends AppError {
  constructor(service: string, message: string) {
    super(ERROR_CODES.EXTERNAL_SERVICE_ERROR, `${service} error: ${message}`, { service })
    this.name = 'ExternalServiceError'
    Object.setPrototypeOf(this, ExternalServiceError.prototype)
  }
}
