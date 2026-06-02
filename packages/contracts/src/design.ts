/**
 * Design Engine shared contracts.
 *
 * Mirrors the backend Pydantic models in
 * apps/workers/src/scalemyprints/domain/design/models.py and
 * apps/workers/src/scalemyprints/api/schemas/design.py.
 *
 * Keep these in sync — both sides use the same field names.
 */

export type DesignStyle =
  | 'vintage'
  | 'minimal'
  | 'bold_typography'
  | 'vector'
  | 'retro_80s'
  | 'kawaii'
  | 'hand_drawn'
  | 'watercolor'
  | 'line_art'
  | 'cyberpunk'
  | 'boho'
  | 'distressed'

export const DESIGN_STYLES: readonly DesignStyle[] = [
  'minimal',
  'bold_typography',
  'vintage',
  'vector',
  'retro_80s',
  'kawaii',
  'hand_drawn',
  'watercolor',
  'line_art',
  'cyberpunk',
  'boho',
  'distressed',
] as const

export const DESIGN_STYLE_LABELS: Record<DesignStyle, string> = {
  minimal: 'Minimal',
  bold_typography: 'Bold Typography',
  vintage: 'Vintage',
  vector: 'Vector',
  retro_80s: 'Retro 80s',
  kawaii: 'Kawaii',
  hand_drawn: 'Hand-Drawn',
  watercolor: 'Watercolor',
  line_art: 'Line Art',
  cyberpunk: 'Cyberpunk',
  boho: 'Boho',
  distressed: 'Distressed',
}

export type DesignAspect = 'square' | 'portrait' | 'landscape' | 't_shirt'

export const DESIGN_ASPECTS: readonly DesignAspect[] = [
  'square',
  't_shirt',
  'portrait',
  'landscape',
] as const

export const DESIGN_ASPECT_LABELS: Record<DesignAspect, string> = {
  square: 'Square (1:1)',
  portrait: 'Portrait (2:3)',
  landscape: 'Landscape (3:2)',
  t_shirt: 'T-Shirt (4:5)',
}

export type DesignStatus =
  | 'queued'
  | 'enriching'
  | 'generating'
  | 'post_processing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export const DESIGN_STATUS_LABELS: Record<DesignStatus, string> = {
  queued: 'Queued',
  enriching: 'Refining prompt',
  generating: 'Generating',
  post_processing: 'Finishing',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export const DESIGN_STATUS_TERMINAL: readonly DesignStatus[] = [
  'completed',
  'failed',
  'cancelled',
] as const

export type DesignOutputFormat = 'png' | 'png_transparent' | 'webp'

export type DesignFailureReason =
  | 'quota_exceeded'
  | 'provider_unavailable'
  | 'provider_rate_limited'
  | 'policy_violation'
  | 'invalid_prompt'
  | 'storage_failure'
  | 'internal'

// ---------------------------------------------------------------------------
// Provenance + artifacts
// ---------------------------------------------------------------------------

export type DesignProviderId =
  | 'disabled'
  | 'fal_flux_schnell'
  | 'fal_flux_pro'
  | 'openai_dalle3'
  | 'replicate_sdxl'

export interface DesignProvenance {
  provider: DesignProviderId
  model: string
  seed: number | null
  enriched_prompt: string
  raw_prompt: string
  style: DesignStyle
  aspect: DesignAspect
  cost_usd: number | null
  duration_ms: number
  safety_filtered: boolean
  moderation_flags: string[]
}

export interface DesignArtifact {
  id: string
  storage_path: string
  public_url: string | null
  thumbnail_url: string | null
  width: number
  height: number
  format: DesignOutputFormat
  bytes_size: number
  provenance: DesignProvenance
}

// ---------------------------------------------------------------------------
// Request / job
// ---------------------------------------------------------------------------

export interface DesignRequest {
  prompt: string
  style: DesignStyle
  aspect: DesignAspect
  output_format: DesignOutputFormat
  variant_count: number
  negative_prompt: string | null
  seed: number | null
  parent_job_id: string | null
}

export interface DesignJob {
  id: string
  user_id: string
  status: DesignStatus
  request: DesignRequest
  enriched_prompt: string | null
  artifacts: DesignArtifact[]
  failure_reason: DesignFailureReason | null
  failure_message: string | null
  providers_attempted: string[]
  plan_at_creation: string | null
  cost_usd_estimate: number | null
  created_at: string
  updated_at: string
  completed_at: string | null
  duration_ms: number
  parent_job_id: string | null
  revision: number
}

export interface DesignJobListItem {
  id: string
  status: DesignStatus
  style: DesignStyle
  aspect: DesignAspect
  prompt: string
  artifact_count: number
  thumbnail_url: string | null
  failure_reason: DesignFailureReason | null
  created_at: string
  completed_at: string | null
}

export interface DesignJobListResponse {
  jobs: DesignJobListItem[]
  total: number
  limit: number
  offset: number
}

// ---------------------------------------------------------------------------
// Generate body
// ---------------------------------------------------------------------------

export interface DesignGenerateBody {
  prompt: string
  style?: DesignStyle
  aspect?: DesignAspect
  output_format?: DesignOutputFormat
  variant_count?: number
  negative_prompt?: string | null
  seed?: number | null
}

// ---------------------------------------------------------------------------
// Quota
// ---------------------------------------------------------------------------

export interface DesignQuota {
  plan: string
  month_bucket: string
  monthly_limit: number  // -1 = unlimited
  used: number
  remaining: number      // -1 = unlimited
  resets_at: string
}

export const DESIGN_QUOTA_UNLIMITED = -1

export function isDesignQuotaUnlimited(limit: number): boolean {
  return limit === DESIGN_QUOTA_UNLIMITED
}

// ---------------------------------------------------------------------------
// Style presets (returned by GET /design/styles)
// ---------------------------------------------------------------------------

export interface DesignStylePreset {
  id: DesignStyle
  label: string
  description: string
}
