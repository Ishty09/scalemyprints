/**
 * Spy — shared contracts (TS).
 *
 * Mirrors apps/workers/src/scalemyprints/domain/spy/{enums,models}.py
 * and apps/workers/src/scalemyprints/api/schemas/spy.py.
 *
 * Keep these in lockstep — both sides use the same field names.
 */

export type Marketplace =
  | 'etsy'
  | 'amazon_merch'
  | 'redbubble'
  | 'teepublic'
  | 'society6'
  | 'zazzle'
  | 'spreadshirt'
  | 'bonanza'

export const MARKETPLACES: readonly Marketplace[] = [
  'etsy',
  'amazon_merch',
  'redbubble',
  'teepublic',
  'society6',
  'zazzle',
  'spreadshirt',
  'bonanza',
] as const

export const MARKETPLACE_LABELS: Record<Marketplace, string> = {
  etsy: 'Etsy',
  amazon_merch: 'Amazon Merch',
  redbubble: 'Redbubble',
  teepublic: 'Teepublic',
  society6: 'Society6',
  zazzle: 'Zazzle',
  spreadshirt: 'Spreadshirt',
  bonanza: 'Bonanza',
}

export type ListingStatus =
  | 'active'
  | 'sold_out'
  | 'inactive'
  | 'delisted'
  | 'unknown'

export type VelocityClass =
  | 'dormant'
  | 'steady'
  | 'rising'
  | 'spiking'
  | 'explosive'

export const VELOCITY_LABELS: Record<VelocityClass, string> = {
  dormant: 'Dormant',
  steady: 'Steady',
  rising: 'Rising',
  spiking: 'Spiking',
  explosive: 'Explosive',
}

export type SaturationClass = 'open' | 'mild' | 'crowded' | 'saturated'

export type ImageMatchType =
  | 'phash_exact'
  | 'phash_near'
  | 'clip_semantic'
  | 'clip_loose'

export const IMAGE_MATCH_LABELS: Record<ImageMatchType, string> = {
  phash_exact: 'Exact match',
  phash_near: 'Near-duplicate',
  clip_semantic: 'Same concept',
  clip_loose: 'Related design',
}

export type SpyFailureReason =
  | 'quota_exceeded'
  | 'source_blocked'
  | 'source_rate_limited'
  | 'invalid_input'
  | 'unsupported_marketplace'
  | 'image_too_large'
  | 'image_invalid'
  | 'embedding_failed'
  | 'storage_failure'
  | 'internal'

export type ViralSource =
  | 'reddit'
  | 'tiktok'
  | 'twitter'
  | 'instagram'
  | 'pinterest'
  | 'youtube_shorts'
  | 'google_trends'

// ---------------------------------------------------------------------------
// Core listing shape
// ---------------------------------------------------------------------------

export interface SpyListingItem {
  marketplace: Marketplace
  external_id: string
  url: string
  title: string
  description: string | null
  tags: string[]
  price_usd: number | null
  currency: string | null
  thumbnail_url: string | null
  shop_handle: string | null
  shop_url: string | null
  status: ListingStatus
  favorites: number | null
  reviews_count: number | null
  rating: number | null
  est_daily_sales: number | null
  velocity_class: VelocityClass
  first_seen_at: string
  last_seen_at: string
}

export interface SpySourceFailure {
  marketplace: Marketplace
  error: string
}

// ---------------------------------------------------------------------------
// POST /api/v1/spy/search
// ---------------------------------------------------------------------------

export interface SpySearchBody {
  text?: string | null
  listing_url?: string | null
  marketplaces?: Marketplace[]
  limit?: number
}

export interface SpySearchResponse {
  listings: SpyListingItem[]
  sources_used: Marketplace[]
  sources_failed: SpySourceFailure[]
  total: number
  duration_ms: number
}

// ---------------------------------------------------------------------------
// POST /api/v1/spy/reverse-image
// ---------------------------------------------------------------------------

export interface ReverseImageMatchItem {
  listing: SpyListingItem
  match_type: ImageMatchType
  phash_distance: number | null
  clip_cosine: number | null
  score: number
}

export interface ReverseImageResponse {
  query_sha256: string
  matches: ReverseImageMatchItem[]
  total: number
  duration_ms: number
  error: string | null
}

// ---------------------------------------------------------------------------
// GET /api/v1/spy/feed
// ---------------------------------------------------------------------------

export interface HotMoverItem {
  id: string
  marketplace: Marketplace
  title: string
  url: string
  thumbnail_url: string | null
  shop_handle: string | null
  shop_url: string | null
  velocity_class: VelocityClass
  est_daily_sales: number | null
  price_usd: number | null
  favorites: number | null
  reviews_count: number | null
  last_seen_at: string
}

export interface HotMoversResponse {
  items: HotMoverItem[]
  total: number
}

// ---------------------------------------------------------------------------
// Shop profile
// ---------------------------------------------------------------------------

export interface ShopProfileItem {
  marketplace: Marketplace
  handle: string
  display_name: string | null
  url: string
  location: string | null
  total_sales: number | null
  listings_count: number | null
  avg_review_rating: number | null
  reviews_count: number | null
  last_seen_at: string
}
