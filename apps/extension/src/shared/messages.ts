/**
 * Messages exchanged between extension contexts.
 *
 * Discriminated union by `type` so handlers narrow exhaustively.
 *
 * Flow:
 *   content   — detects listing page, asks background for a search
 *   background — calls the API (avoids CORS in content), returns result
 *   popup      — reads stored stats, shows quota / sign-up CTA
 */

import type {
  TrademarkSearchRequest,
  TrademarkSearchResponse,
} from '@scalemyprints/contracts'

export type SearchTrademarkRequest = {
  type: 'search_trademark'
  request: TrademarkSearchRequest
}

export type SearchTrademarkResponse =
  | { ok: true; data: TrademarkSearchResponse }
  | { ok: false; error: { code: string; message: string } }

export type GetUsageStatsRequest = {
  type: 'get_usage_stats'
}

export type UsageStats = {
  searches_today: number
  searches_total: number
  last_search_at: string | null
}

export type GetUsageStatsResponse = {
  ok: true
  data: UsageStats
}

export type ExtensionMessage = SearchTrademarkRequest | GetUsageStatsRequest

export type ExtensionResponse<T extends ExtensionMessage> =
  T extends SearchTrademarkRequest ? SearchTrademarkResponse :
  T extends GetUsageStatsRequest ? GetUsageStatsResponse :
  never
