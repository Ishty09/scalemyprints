/**
 * @scalemyprints/contracts
 *
 * Shared type contracts — source of truth between web, workers, and extension.
 *
 * IMPORTANT:
 * - All types here must have matching Pydantic models in apps/workers.
 * - Zod schemas are preferred for runtime validation at boundaries.
 * - Never import app-specific types here.
 */

export * from './branding'
export * from './pricing'
export * from './api'
export * from './auth'
export * from './trademark'
export * from './niche'
export * from './errors'
