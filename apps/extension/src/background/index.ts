/**
 * Background service worker.
 *
 * Acts as a privileged proxy for content scripts:
 * - Owns API requests (host_permissions are granted at this level)
 * - Maintains usage stats in chrome.storage
 * - Caches results to reduce API hits
 *
 * Manifest V3 service workers are short-lived; everything must be
 * stateless across invocations. State lives in chrome.storage.
 */

import { CONFIG } from '@/shared/config'
import {
  buildCacheKey,
  getCachedResult,
  getUsageStats,
  recordSearch,
  setCachedResult,
} from '@/shared/storage'
import type {
  ExtensionMessage,
  GetUsageStatsResponse,
  SearchTrademarkRequest,
  SearchTrademarkResponse,
} from '@/shared/messages'

// ---------------------------------------------------------------------------
// Message router
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message: ExtensionMessage, _sender, sendResponse) => {
  // chrome.runtime.onMessage requires returning `true` to indicate async reply
  void handleMessage(message).then(sendResponse)
  return true
})

async function handleMessage(message: ExtensionMessage): Promise<unknown> {
  switch (message.type) {
    case 'search_trademark':
      return handleSearchTrademark(message)
    case 'get_usage_stats':
      return handleGetUsageStats()
    default: {
      // Exhaustiveness check — TS will error if a new message type isn't handled
      const _exhaustive: never = message
      return { ok: false, error: { code: 'unknown_message', message: 'Unknown message type' } }
    }
  }
}

// ---------------------------------------------------------------------------
// Trademark search handler
// ---------------------------------------------------------------------------

async function handleSearchTrademark(
  message: SearchTrademarkRequest,
): Promise<SearchTrademarkResponse> {
  const { request } = message
  const cacheKey = buildCacheKey(request.phrase, request.jurisdictions)

  // 1. Try cache first
  try {
    const cached = await getCachedResult(cacheKey, CONFIG.resultCacheMinutes)
    if (cached) {
      return { ok: true, data: { ...cached, from_cache: true } }
    }
  } catch {
    // Cache failure is non-fatal — continue to API
  }

  // 2. Quota check (free tier limit)
  try {
    const stats = await getUsageStats()
    if (stats.searches_today >= CONFIG.freeSearchesPerDay) {
      return {
        ok: false,
        error: {
          code: 'quota_exceeded',
          message: `Daily limit reached (${CONFIG.freeSearchesPerDay} free searches). Sign up for more.`,
        },
      }
    }
  } catch {
    // Treat storage failure as non-blocking
  }

  // 3. Hit the API
  try {
    const response = await fetch(`${CONFIG.apiUrl}/api/v1/trademark/search`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(request),
    })

    const payload = await response.json()
    if (!payload || typeof payload !== 'object' || !('ok' in payload)) {
      return {
        ok: false,
        error: { code: 'malformed_response', message: 'Server returned unexpected payload' },
      }
    }

    if (payload.ok === false) {
      return {
        ok: false,
        error: {
          code: payload.error?.code ?? 'unknown_error',
          message: payload.error?.message ?? 'Request failed',
        },
      }
    }

    // Success — record stats and cache
    try {
      await recordSearch()
      await setCachedResult(cacheKey, payload.data)
    } catch {
      // Non-fatal
    }

    return { ok: true, data: payload.data }
  } catch (err) {
    return {
      ok: false,
      error: {
        code: 'network_error',
        message: err instanceof Error ? err.message : 'Network error',
      },
    }
  }
}

// ---------------------------------------------------------------------------
// Stats handler
// ---------------------------------------------------------------------------

async function handleGetUsageStats(): Promise<GetUsageStatsResponse> {
  const stats = await getUsageStats()
  return { ok: true, data: stats }
}

// ---------------------------------------------------------------------------
// Lifecycle hooks
// ---------------------------------------------------------------------------

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    // Open welcome page on first install
    chrome.tabs.create({ url: `${CONFIG.marketingUrl}/extension-welcome` })
  }
})
