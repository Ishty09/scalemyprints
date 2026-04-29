/**
 * Popup script.
 *
 * Renders quota status + signup CTA when the user clicks the toolbar icon.
 * Uses plain DOM rather than React to keep the popup bundle tiny.
 */

import { CONFIG } from '@/shared/config'
import type { GetUsageStatsRequest, GetUsageStatsResponse } from '@/shared/messages'

bootstrap()

async function bootstrap() {
  const root = document.getElementById('root')
  if (!root) return

  const message: GetUsageStatsRequest = { type: 'get_usage_stats' }
  let stats = { searches_today: 0, searches_total: 0, last_search_at: null as string | null }
  try {
    const response = (await chrome.runtime.sendMessage(message)) as GetUsageStatsResponse
    if (response.ok) stats = response.data
  } catch {
    // Storage error — show defaults
  }

  const remaining = Math.max(0, CONFIG.freeSearchesPerDay - stats.searches_today)
  const isOverQuota = remaining === 0
  const usageColor = remaining <= 1 ? 'warning' : ''

  root.innerHTML = `
    <div class="container">
      <div class="header">
        <span class="logo">SMP</span>
        <span class="brand">ScaleMyPrints</span>
      </div>

      <p class="tagline">
        Free trademark checker on Etsy, Amazon, and Redbubble listings.
      </p>

      <div class="stat-card">
        <div class="stat-row">
          <span class="stat-label">Searches today</span>
          <span class="stat-value ${usageColor}">
            ${stats.searches_today} / ${CONFIG.freeSearchesPerDay}
          </span>
        </div>
        <div class="stat-row" style="margin-top: 6px;">
          <span class="stat-label">Total checks</span>
          <span class="stat-value">${stats.searches_total}</span>
        </div>
      </div>

      ${
        isOverQuota
          ? `<a class="cta" href="${CONFIG.marketingUrl}/signup?ref=ext-quota" target="_blank">
               Upgrade — unlimited checks
             </a>`
          : `<a class="cta" href="${CONFIG.marketingUrl}/signup?ref=ext" target="_blank">
               Get full access free
             </a>`
      }

      <a class="secondary-link" href="${CONFIG.marketingUrl}/dashboard/trademark" target="_blank">
        Open dashboard →
      </a>

      <div class="footer">
        Visit any listing on Etsy or Amazon to use.
        <br />
        Powered by <a href="${CONFIG.marketingUrl}" target="_blank">scalemyprints.com</a>
      </div>
    </div>
  `
}
