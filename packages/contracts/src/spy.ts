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

// ---------------------------------------------------------------------------
// Shop audit
// ---------------------------------------------------------------------------

export interface TagFrequencyItem {
  tag: string
  count: number
}

export interface ShopAuditBody {
  marketplace: Marketplace
  handle: string
  depth?: 'shallow' | 'standard' | 'deep'
}

export interface ShopAuditResponse {
  shop: ShopProfileItem
  depth: string
  listings_sampled: number
  est_monthly_revenue_usd: number | null
  avg_price_usd: number | null
  new_listings_last_30d: number | null
  restock_cadence_days: number | null
  top_listings: SpyListingItem[]
  most_used_tags: TagFrequencyItem[]
  captured_at: string
  error: string | null
}

// ---------------------------------------------------------------------------
// Saturation / difficulty score
// ---------------------------------------------------------------------------

export interface SaturationBody {
  phrase?: string | null
  listing_ids?: string[]
  marketplaces?: Marketplace[]
  use_live_search?: boolean
}

export interface SaturationResponse {
  score: number              // 0-100
  saturation_class: SaturationClass
  listings_count: number
  unique_shops: number
  hhi: number
  gmv_pool_usd: number
  density_component: number
  concentration_component: number
  velocity_component: number
  recency_component: number
  explanation: string
}

// ---------------------------------------------------------------------------
// Profit calculator
// ---------------------------------------------------------------------------

export type ProductType =
  | 't_shirt'
  | 'tank_top'
  | 'long_sleeve'
  | 'hoodie'
  | 'sweatshirt'
  | 'mug_11oz'
  | 'mug_15oz'
  | 'tote_bag'
  | 'phone_case'
  | 'poster_18x24'
  | 'sticker'
  | 'blanket_50x60'
  | 'pillow_18x18'

export type PrinterId =
  | 'printful'
  | 'printify'
  | 'gelato'
  | 'customcat'
  | 'spod'

export const PRINTERS: readonly PrinterId[] = [
  'printify',
  'printful',
  'gelato',
  'customcat',
  'spod',
] as const

export const PRINTER_LABELS: Record<PrinterId, string> = {
  printify: 'Printify',
  printful: 'Printful',
  gelato: 'Gelato',
  customcat: 'CustomCat',
  spod: 'SPOD',
}

export const PRODUCT_LABELS: Record<ProductType, string> = {
  t_shirt: 'T-Shirt',
  tank_top: 'Tank Top',
  long_sleeve: 'Long Sleeve',
  hoodie: 'Hoodie',
  sweatshirt: 'Sweatshirt',
  mug_11oz: 'Mug (11oz)',
  mug_15oz: 'Mug (15oz)',
  tote_bag: 'Tote Bag',
  phone_case: 'Phone Case',
  poster_18x24: 'Poster (18×24)',
  sticker: 'Sticker',
  blanket_50x60: 'Blanket (50×60)',
  pillow_18x18: 'Pillow (18×18)',
}

export interface ProfitBody {
  marketplace: Marketplace
  product_type: ProductType
  sale_price_usd: number
  printer?: PrinterId
  shipping_usd?: number
  ad_cpc_usd?: number
  ad_conversion_rate?: number
}

export interface ProfitResponse {
  sale_price_usd: number
  base_cost_usd: number
  marketplace_fee_usd: number
  shipping_usd: number
  ad_cost_usd: number
  profit_usd: number
  margin_pct: number
  printer: PrinterId
  note: string | null
}

// ---------------------------------------------------------------------------
// Ad library
// ---------------------------------------------------------------------------

export type AdPlatform =
  | 'facebook'
  | 'instagram'
  | 'tiktok'
  | 'pinterest'
  | 'google_ads'

export interface AdSpyHitItem {
  platform: AdPlatform
  ad_id: string
  page_or_handle: string
  page_id: string | null
  primary_text: string | null
  cta: string | null
  landing_url: string | null
  started_at: string | null
  last_seen_at: string | null
  impressions_lower: number | null
  impressions_upper: number | null
  countries: string[]
}

export interface AdLibraryResponse {
  platform: AdPlatform
  hits: AdSpyHitItem[]
  total: number
  duration_ms: number
  error: string | null
}

// ---------------------------------------------------------------------------
// Velocity refresh (cron-only)
// ---------------------------------------------------------------------------

export interface VelocityRefreshResponse {
  started_at: string
  completed_at: string
  duration_ms: number
  candidates: number
  refreshed: number
  failed: number
  spikes_detected: number
  by_marketplace: Record<string, number>
  errors: string[]
}

// ---------------------------------------------------------------------------
// Phase 3 — viral mining, tag mining, TM overlay
// ---------------------------------------------------------------------------

export interface ViralSignalItem {
  source: ViralSource
  source_url: string | null
  phrase: string
  detected_at: string
  engagement: number
  momentum_score: number
  pod_readiness_score: number
  existing_pod_count: number
  suggested_styles: string[]
  note: string | null
}

export interface ViralFeedResponse {
  signals: ViralSignalItem[]
  sources_used: string[]
  sources_failed: { source: string; error: string }[]
  total: number
  duration_ms: number
}

export interface TagMineBody {
  seed: string
  marketplaces?: Marketplace[]
  per_marketplace_limit?: number
  top_n?: number
}

export interface MinedTagItem {
  tag: string
  total_count: number
  by_marketplace: Record<string, number>
  distinct_marketplaces: number
  sample_listings: string[]
}

export interface TagMineResponse {
  seed: string
  tags: MinedTagItem[]
  total_listings_scanned: number
  duration_ms: number
}

export interface TMOverlayBody {
  phrase: string
  marketplaces?: Marketplace[]
  nice_classes?: number[]
}

export type TMOverlayVerdict = 'go' | 'caution' | 'block'

export interface TMOverlayResponse {
  phrase: string
  opportunity_score: number
  risk_score: number
  saturation_score: number
  combined_verdict: TMOverlayVerdict
  listings_count: number
  est_monthly_gmv_usd: number
  trademark: {
    overall_risk_level: string
    overall_risk_score: number
    jurisdictions: {
      code: string
      risk_score: number
      risk_level: string
      match_count: number
      error: string | null
    }[]
    recommendations: {
      severity: string
      message: string
    }[]
  }
  duration_ms: number
}
