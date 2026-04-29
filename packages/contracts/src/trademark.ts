import { z } from 'zod'

/**
 * Trademark Shield contracts.
 *
 * Contract between frontend (search UI, dashboard, Chrome extension)
 * and backend (Python workers that query USPTO/EUIPO/ATMOSS).
 *
 * IMPORTANT: Pydantic models in apps/workers/src/scalemyprints/domain/trademark/models.py
 * MUST mirror these schemas field-for-field.
 */

// ---------------------------------------------------------------------------
// Jurisdictions and classifications
// ---------------------------------------------------------------------------

export const JURISDICTION_CODE_SCHEMA = z.enum(['US', 'EU', 'UK', 'AU'])
export type JurisdictionCode = z.infer<typeof JURISDICTION_CODE_SCHEMA>

export const JURISDICTION_NAMES: Record<JurisdictionCode, string> = {
  US: 'United States',
  EU: 'European Union',
  UK: 'United Kingdom',
  AU: 'Australia',
}

/** Nice classification — 1-45. Most relevant for POD:
 *  16 = paper goods, stickers
 *  21 = drinkware (mugs)
 *  25 = apparel (t-shirts, hoodies)
 *  28 = toys, games
 */
export const NICE_CLASS_SCHEMA = z.number().int().min(1).max(45)
export type NiceClass = z.infer<typeof NICE_CLASS_SCHEMA>

export const POD_RELEVANT_NICE_CLASSES: Record<NiceClass, string> = {
  9: 'Electronics, phone cases',
  14: 'Jewelry',
  16: 'Paper goods, stickers, prints',
  18: 'Bags, leather goods',
  20: 'Furniture, pillows',
  21: 'Drinkware (mugs, tumblers)',
  24: 'Textiles, blankets',
  25: 'Apparel (t-shirts, hoodies)',
  28: 'Toys, games',
  41: 'Education, entertainment',
} as const

// ---------------------------------------------------------------------------
// Risk levels and scores
// ---------------------------------------------------------------------------

export const RISK_LEVEL_SCHEMA = z.enum(['safe', 'low', 'medium', 'high', 'critical'])
export type RiskLevel = z.infer<typeof RISK_LEVEL_SCHEMA>

/** Score buckets — must match RiskScorer._score_to_level in Python */
export const RISK_LEVEL_THRESHOLDS = {
  safe: { min: 0, max: 20 },
  low: { min: 21, max: 40 },
  medium: { min: 41, max: 60 },
  high: { min: 61, max: 80 },
  critical: { min: 81, max: 100 },
} as const

export function scoreToRiskLevel(score: number): RiskLevel {
  if (score <= 20) return 'safe'
  if (score <= 40) return 'low'
  if (score <= 60) return 'medium'
  if (score <= 80) return 'high'
  return 'critical'
}

// ---------------------------------------------------------------------------
// Filing status — normalized across jurisdictions
// ---------------------------------------------------------------------------

export const FILING_STATUS_SCHEMA = z.enum([
  'registered', // active, fully protected
  'pending', // filed, under examination
  'opposed', // published, under opposition
  'abandoned', // dropped by applicant
  'cancelled', // cancelled by office
  'expired', // no longer renewed
  'unknown', // could not parse
])
export type FilingStatus = z.infer<typeof FILING_STATUS_SCHEMA>

// ---------------------------------------------------------------------------
// Individual trademark record (one hit from a jurisdiction search)
// ---------------------------------------------------------------------------

export const TRADEMARK_RECORD_SCHEMA = z.object({
  /** Serial/registration number from the issuing office */
  registration_number: z.string(),
  /** The mark text (normalized) */
  mark: z.string(),
  /** Owner organization or individual */
  owner: z.string().nullable(),
  /** Normalized status (see FILING_STATUS) */
  status: FILING_STATUS_SCHEMA,
  /** Raw status string from source (for display/debugging) */
  raw_status: z.string().nullable(),
  /** Primary Nice class */
  nice_class: NICE_CLASS_SCHEMA.nullable(),
  /** All Nice classes this mark covers */
  nice_classes: z.array(NICE_CLASS_SCHEMA),
  /** ISO date strings */
  filing_date: z.string().nullable(),
  registration_date: z.string().nullable(),
  /** Jurisdiction this record came from */
  jurisdiction: JURISDICTION_CODE_SCHEMA,
  /** Deep link to the original filing at the source office */
  source_url: z.string().url().nullable(),
  /** Goods & services description (may be long) */
  goods_services: z.string().nullable(),
  /** Computed flags for UI convenience */
  is_active: z.boolean(),
  is_pending: z.boolean(),
})
export type TrademarkRecord = z.infer<typeof TRADEMARK_RECORD_SCHEMA>

// ---------------------------------------------------------------------------
// Per-jurisdiction risk analysis
// ---------------------------------------------------------------------------

export const JURISDICTION_RISK_SCHEMA = z.object({
  code: JURISDICTION_CODE_SCHEMA,
  /** Score 0-100 for this jurisdiction alone */
  risk_score: z.number().int().min(0).max(100),
  risk_level: RISK_LEVEL_SCHEMA,
  /** Counts */
  active_registrations: z.number().int().min(0),
  pending_applications: z.number().int().min(0),
  adjacent_class_registrations: z.number().int().min(0),
  /** Common-law use density in this market (0-1) */
  common_law_density: z.number().min(0).max(1).nullable(),
  /** If true, it's safe to sell here despite risk elsewhere */
  arbitrage_available: z.boolean(),
  /** The actual matching records (for user to inspect) */
  matching_records: z.array(TRADEMARK_RECORD_SCHEMA),
  /** Analysis metadata */
  search_duration_ms: z.number().int().nullable(),
  /** If API failed for this jurisdiction */
  error: z.string().nullable(),
})
export type JurisdictionRisk = z.infer<typeof JURISDICTION_RISK_SCHEMA>

// ---------------------------------------------------------------------------
// Request — what the client sends
// ---------------------------------------------------------------------------

export const TRADEMARK_SEARCH_REQUEST_SCHEMA = z.object({
  phrase: z
    .string()
    .trim()
    .min(1, 'Phrase is required')
    .max(200, 'Phrase too long (max 200 characters)'),
  jurisdictions: z
    .array(JURISDICTION_CODE_SCHEMA)
    .min(1, 'At least one jurisdiction required')
    .default(['US', 'EU', 'AU']),
  nice_classes: z.array(NICE_CLASS_SCHEMA).min(1).default([25, 21]),
  check_common_law: z.boolean().default(true),
})
export type TrademarkSearchRequest = z.infer<typeof TRADEMARK_SEARCH_REQUEST_SCHEMA>

// ---------------------------------------------------------------------------
// Response — what the backend returns
// ---------------------------------------------------------------------------

export const TRADEMARK_RECOMMENDATION_SCHEMA = z.object({
  severity: z.enum(['info', 'warning', 'danger', 'success']),
  message: z.string(),
  action: z.string().nullable(),
})
export type TrademarkRecommendation = z.infer<typeof TRADEMARK_RECOMMENDATION_SCHEMA>

export const TRADEMARK_SEARCH_RESPONSE_SCHEMA = z.object({
  /** Echo of the phrase analyzed */
  phrase: z.string(),
  /** Max risk across user's target jurisdictions (they can be sued anywhere) */
  overall_risk_score: z.number().int().min(0).max(100),
  overall_risk_level: RISK_LEVEL_SCHEMA,
  /** Per-jurisdiction breakdown */
  jurisdictions: z.array(JURISDICTION_RISK_SCHEMA),
  /** Human-readable, actionable */
  recommendations: z.array(TRADEMARK_RECOMMENDATION_SCHEMA),
  /** 0-1 score: how generic/descriptive (lower genericness = higher risk) */
  phrase_genericness: z.number().min(0).max(1),
  /** Nice classes searched */
  nice_classes_searched: z.array(NICE_CLASS_SCHEMA),
  /** ISO timestamp of analysis */
  analyzed_at: z.string().datetime(),
  /** Whether result was served from cache */
  from_cache: z.boolean(),
  /** Total search time in milliseconds */
  duration_ms: z.number().int(),
})
export type TrademarkSearchResponse = z.infer<typeof TRADEMARK_SEARCH_RESPONSE_SCHEMA>

// ---------------------------------------------------------------------------
// Monitor (ongoing alerting)
// ---------------------------------------------------------------------------

export const MONITOR_FREQUENCY_SCHEMA = z.enum(['daily', 'weekly', 'monthly'])
export type MonitorFrequency = z.infer<typeof MONITOR_FREQUENCY_SCHEMA>

export const TRADEMARK_MONITOR_SCHEMA = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  phrase: z.string(),
  jurisdictions: z.array(JURISDICTION_CODE_SCHEMA),
  nice_classes: z.array(NICE_CLASS_SCHEMA),
  frequency: MONITOR_FREQUENCY_SCHEMA,
  alert_email: z.string().email().nullable(),
  alert_webhook_url: z.string().url().nullable(),
  is_active: z.boolean(),
  last_checked_at: z.string().datetime().nullable(),
  created_at: z.string().datetime(),
})
export type TrademarkMonitor = z.infer<typeof TRADEMARK_MONITOR_SCHEMA>

export const CREATE_MONITOR_REQUEST_SCHEMA = z.object({
  phrase: z.string().min(1).max(200),
  jurisdictions: z.array(JURISDICTION_CODE_SCHEMA).min(1),
  nice_classes: z.array(NICE_CLASS_SCHEMA).min(1),
  frequency: MONITOR_FREQUENCY_SCHEMA.default('weekly'),
  alert_email: z.string().email().nullable().optional(),
})
export type CreateMonitorRequest = z.infer<typeof CREATE_MONITOR_REQUEST_SCHEMA>

// ---------------------------------------------------------------------------
// Search history
// ---------------------------------------------------------------------------

export const SEARCH_HISTORY_ITEM_SCHEMA = z.object({
  id: z.string().uuid(),
  phrase: z.string(),
  overall_risk_score: z.number().int().min(0).max(100),
  overall_risk_level: RISK_LEVEL_SCHEMA,
  jurisdictions_searched: z.array(JURISDICTION_CODE_SCHEMA),
  analyzed_at: z.string().datetime(),
})
export type SearchHistoryItem = z.infer<typeof SEARCH_HISTORY_ITEM_SCHEMA>

// ---------------------------------------------------------------------------
// UI styling helpers — keeps presentation consistent
// ---------------------------------------------------------------------------

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  safe: 'Safe',
  low: 'Low Risk',
  medium: 'Medium Risk',
  high: 'High Risk',
  critical: 'Critical Risk',
}

export const RISK_LEVEL_COLORS: Record<RiskLevel, { bg: string; text: string; border: string }> = {
  safe: { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' },
  low: { bg: '#eff6ff', text: '#1d4ed8', border: '#bfdbfe' },
  medium: { bg: '#fffbeb', text: '#b45309', border: '#fcd34d' },
  high: { bg: '#fff7ed', text: '#c2410c', border: '#fdba74' },
  critical: { bg: '#fef2f2', text: '#b91c1c', border: '#fca5a5' },
}
