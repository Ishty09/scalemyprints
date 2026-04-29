/**
 * Niche Radar shared contracts.
 *
 * Mirrors the backend Pydantic models in
 * apps/workers/src/scalemyprints/domain/niche/models.py
 *
 * Keep these in sync — both sides use the same field names.
 */

export type NicheCountry = 'US' | 'UK' | 'AU' | 'CA' | 'DE'

export const NICHE_COUNTRIES: readonly NicheCountry[] = ['US', 'UK', 'AU', 'CA', 'DE'] as const

export const COUNTRY_LABELS: Record<NicheCountry, string> = {
  US: 'United States',
  UK: 'United Kingdom',
  AU: 'Australia',
  CA: 'Canada',
  DE: 'Germany',
}

export type NicheHealth = 'hot' | 'promising' | 'moderate' | 'weak' | 'avoid'

export type TrendDirection = 'rising' | 'stable' | 'declining'

export type CompetitionLevel = 'low' | 'medium' | 'high' | 'saturated'

export type EventCategory =
  | 'holiday'
  | 'religious'
  | 'cultural'
  | 'sports'
  | 'awareness'
  | 'seasonal'
  | 'school'
  | 'quirky'

export const EVENT_CATEGORY_LABELS: Record<EventCategory, string> = {
  holiday: 'Holiday',
  religious: 'Religious',
  cultural: 'Cultural',
  sports: 'Sports',
  awareness: 'Awareness',
  seasonal: 'Seasonal',
  school: 'School',
  quirky: 'Quirky',
}

export interface DemandSignal {
  score: number
  search_volume_index: number
  listing_count: number | null
  source: string
}

export interface TrendSignal {
  score: number
  direction: TrendDirection
  growth_pct_90d: number | null
  sample_points: number
}

export interface CompetitionSignal {
  score: number
  level: CompetitionLevel
  listing_count: number | null
  unique_sellers_estimate: number | null
  avg_listing_age_days: number | null
}

export interface ProfitabilitySignal {
  score: number
  avg_price_usd: number | null
  estimated_margin_usd: number | null
  sample_size: number
}

export interface SeasonalitySignal {
  score: number
  nearest_event_name: string | null
  nearest_event_date: string | null
  days_until_event: number | null
}

export interface NicheEvent {
  id: string
  country: NicheCountry
  event_date: string
  name: string
  category: EventCategory
  description: string | null
  pod_relevance_score: number
  suggested_niches: string[]
}

export interface NicheRecord {
  keyword: string
  country: NicheCountry
  nhs_score: number
  health: NicheHealth
  demand: DemandSignal
  trend: TrendSignal
  competition: CompetitionSignal
  profitability: ProfitabilitySignal
  seasonality: SeasonalitySignal
  related_keywords: string[]
  sample_listings_urls: string[]
  upcoming_events: NicheEvent[]
  analyzed_at: string
  duration_ms: number
  data_sources_used: string[]
  degraded: boolean
}

export interface NicheSearchRequest {
  keyword: string
  country: NicheCountry
}

export type NicheSearchResponse = NicheRecord

export interface EventListItem {
  id: string
  country: NicheCountry
  event_date: string
  name: string
  category: EventCategory
  pod_relevance_score: number
  suggested_niches: string[]
  days_until: number
}

export type EventListResponse = EventListItem[]

export interface NicheExpansionRequest {
  seed_keyword: string
  country: NicheCountry
  max_suggestions?: number
}

export interface NicheExpansionResponse {
  seed_keyword: string
  country: NicheCountry
  suggestions: string[]
  rationale: string | null
  duration_ms: number
}
