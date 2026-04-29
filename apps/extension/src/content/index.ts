/**
 * Content script — injects the trademark check widget on listing pages.
 *
 * Strategy:
 * 1. Wait for DOM idle, detect listing via detect-listing.ts
 * 2. Inject a Shadow DOM-isolated widget so host page styles can't break us
 * 3. On user click, send `search_trademark` message to background
 * 4. Render result inline with severity colors + CTA to upgrade
 *
 * Re-runs on URL changes (Etsy uses pushState navigation between listings).
 */

import type {
  JurisdictionRisk,
  TrademarkSearchResponse,
} from '@scalemyprints/contracts'

import { CONFIG } from '@/shared/config'
import type {
  SearchTrademarkRequest,
  SearchTrademarkResponse,
} from '@/shared/messages'

import { detectListing, type ListingInfo } from './detect-listing'

const WIDGET_ID = 'smp-tm-widget'
const SHADOW_HOST_ID = 'smp-tm-shadow-host'

// State per page (shadow root, last listing seen)
let mountedListingTitle: string | null = null

bootstrap()

function bootstrap() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryMount)
  } else {
    tryMount()
  }

  // Etsy/Amazon use SPA navigation. Watch for URL/title changes and remount.
  hookSpaNavigation()
}

function hookSpaNavigation() {
  let lastUrl = window.location.href
  const observer = new MutationObserver(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href
      // Allow the new page to render
      setTimeout(tryMount, 600)
    }
  })
  observer.observe(document.body, { childList: true, subtree: true })
}

function tryMount() {
  const listing = detectListing()
  if (!listing) {
    unmount()
    mountedListingTitle = null
    return
  }
  // Skip if same listing — prevents flicker on re-render
  if (mountedListingTitle === listing.title) return
  mountedListingTitle = listing.title

  unmount()
  mount(listing)
}

function unmount() {
  document.getElementById(SHADOW_HOST_ID)?.remove()
}

// ---------------------------------------------------------------------------
// Mount widget into Shadow DOM (style isolation)
// ---------------------------------------------------------------------------

function mount(listing: ListingInfo) {
  const host = document.createElement('div')
  host.id = SHADOW_HOST_ID
  host.style.cssText = 'all: initial; position: fixed; bottom: 20px; right: 20px; z-index: 2147483647;'
  document.body.appendChild(host)

  const shadow = host.attachShadow({ mode: 'open' })
  shadow.innerHTML = renderInitialWidget(listing)

  // Wire up click handler
  const button = shadow.getElementById('smp-check-btn')
  button?.addEventListener('click', () => handleCheck(shadow, listing))
}

function renderInitialWidget(listing: ListingInfo): string {
  return `
    <style>${WIDGET_STYLES}</style>
    <div id="${WIDGET_ID}" class="widget" role="region" aria-label="Trademark check">
      <div class="header">
        <span class="logo">SMP</span>
        <span class="title">Trademark Check</span>
        <button class="close" id="smp-close" aria-label="Close">&times;</button>
      </div>
      <div class="body" id="smp-body">
        <p class="phrase">${escapeHtml(truncate(listing.title, 80))}</p>
        <button class="primary-btn" id="smp-check-btn">⚡ Check trademark risk</button>
        <p class="hint">${CONFIG.freeSearchesPerDay} free checks/day. No login required.</p>
      </div>
      <div class="footer">
        Powered by <a href="${CONFIG.marketingUrl}" target="_blank" rel="noopener noreferrer">ScaleMyPrints</a>
      </div>
    </div>
  `
}

// ---------------------------------------------------------------------------
// Handle check action
// ---------------------------------------------------------------------------

async function handleCheck(shadow: ShadowRoot, listing: ListingInfo) {
  const body = shadow.getElementById('smp-body')
  if (!body) return

  // Loading state
  body.innerHTML = `
    <div class="loading">
      <div class="spinner" aria-hidden="true"></div>
      <p>Checking USPTO, EUIPO, IP Australia...</p>
    </div>
  `

  // Send to background worker
  const message: SearchTrademarkRequest = {
    type: 'search_trademark',
    request: {
      phrase: listing.title,
      jurisdictions: ['US', 'EU', 'AU'],
      nice_classes: listing.niceClasses,
      check_common_law: false,
    },
  }

  let response: SearchTrademarkResponse
  try {
    response = (await chrome.runtime.sendMessage(message)) as SearchTrademarkResponse
  } catch (err) {
    body.innerHTML = renderError('extension_error', 'Could not reach the extension service')
    return
  }

  if (!response.ok) {
    body.innerHTML = renderError(response.error.code, response.error.message)
    return
  }

  body.innerHTML = renderResult(response.data)
}

// ---------------------------------------------------------------------------
// Result rendering
// ---------------------------------------------------------------------------

function renderResult(result: TrademarkSearchResponse): string {
  const colors: Record<string, string> = {
    safe: '#10b981',
    low: '#3b82f6',
    medium: '#f59e0b',
    high: '#f97316',
    critical: '#ef4444',
  }
  const icons: Record<string, string> = {
    safe: '✅',
    low: '✅',
    medium: 'ℹ️',
    high: '⚠️',
    critical: '🚫',
  }
  const color = colors[result.overall_risk_level] ?? '#64748b'
  const icon = icons[result.overall_risk_level] ?? '•'

  const jurisdictions = result.jurisdictions
    .map((j) => renderJurisdictionPill(j))
    .join('')

  const topRecs = result.recommendations
    .slice(0, 2)
    .map((r) => `<li>${escapeHtml(r.message)}</li>`)
    .join('')

  return `
    <div class="result" style="--accent: ${color}">
      <div class="result-header">
        <span class="result-icon">${icon}</span>
        <span class="result-level">${escapeHtml(result.overall_risk_level.toUpperCase())} RISK</span>
      </div>
      <div class="result-score">${result.overall_risk_score}<span>/100</span></div>
      <div class="result-jurisdictions">${jurisdictions}</div>
      ${topRecs ? `<ul class="result-recs">${topRecs}</ul>` : ''}
      <a class="result-cta" href="${CONFIG.marketingUrl}/dashboard/trademark?phrase=${encodeURIComponent(result.phrase)}" target="_blank" rel="noopener noreferrer">
        View full analysis →
      </a>
    </div>
  `
}

function renderJurisdictionPill(j: JurisdictionRisk): string {
  if (j.error) {
    return `<span class="juris juris-error" title="${escapeHtml(j.error)}">${j.code}: —</span>`
  }
  const score = j.risk_score
  const color = score < 30 ? '#10b981' : score < 60 ? '#f59e0b' : '#ef4444'
  return `<span class="juris" style="--c: ${color}">${j.code}: ${score}</span>`
}

function renderError(code: string, message: string): string {
  const ctaHref = code === 'quota_exceeded'
    ? `${CONFIG.marketingUrl}/signup?ref=ext`
    : null
  return `
    <div class="error">
      <p class="error-msg">${escapeHtml(message)}</p>
      ${ctaHref ? `<a class="primary-btn-link" href="${ctaHref}" target="_blank" rel="noopener noreferrer">Sign up free for more checks →</a>` : ''}
    </div>
  `
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen - 1).trimEnd() + '…'
}

// ---------------------------------------------------------------------------
// Styles (inlined into shadow root)
// ---------------------------------------------------------------------------

const WIDGET_STYLES = `
  :host { all: initial; }
  * { box-sizing: border-box; }
  .widget {
    width: 320px;
    background: #fff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
    box-shadow: 0 10px 40px rgba(15, 23, 42, 0.18);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 14px;
    color: #0f172a;
    overflow: hidden;
  }
  .header {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 14px;
    border-bottom: 1px solid #f1f5f9;
  }
  .logo {
    background: linear-gradient(135deg, #0d9488, #f97316);
    color: #fff;
    font-weight: 700;
    font-size: 11px;
    padding: 3px 6px;
    border-radius: 4px;
  }
  .title { font-weight: 600; color: #334155; flex: 1; }
  .close {
    background: none; border: none; color: #94a3b8;
    cursor: pointer; font-size: 20px; line-height: 1;
    padding: 0 4px;
  }
  .close:hover { color: #0f172a; }
  .body { padding: 14px; }
  .phrase {
    font-size: 12px; color: #64748b;
    margin: 0 0 10px 0; line-height: 1.4;
  }
  .primary-btn {
    width: 100%;
    background: #0d9488; color: #fff;
    border: none; padding: 10px;
    border-radius: 8px;
    font-weight: 600; font-size: 14px;
    cursor: pointer;
    transition: background 120ms ease;
  }
  .primary-btn:hover { background: #0f766e; }
  .primary-btn-link {
    display: block; width: 100%;
    background: #0d9488; color: #fff;
    text-align: center;
    padding: 10px; border-radius: 8px;
    font-weight: 600; font-size: 13px;
    text-decoration: none;
    transition: background 120ms ease;
  }
  .primary-btn-link:hover { background: #0f766e; }
  .hint { font-size: 11px; color: #94a3b8; margin: 8px 0 0 0; text-align: center; }
  .footer {
    text-align: center;
    font-size: 11px; color: #94a3b8;
    padding: 8px;
    border-top: 1px solid #f1f5f9;
  }
  .footer a { color: #0d9488; text-decoration: none; font-weight: 500; }
  .footer a:hover { text-decoration: underline; }

  .loading { text-align: center; padding: 24px 0; }
  .spinner {
    width: 24px; height: 24px;
    border: 3px solid #e2e8f0;
    border-top-color: #0d9488;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 12px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .result-header {
    display: flex; align-items: center; gap: 8px;
    color: var(--accent);
    font-weight: 700; font-size: 12px;
    letter-spacing: 0.04em;
    margin-bottom: 2px;
  }
  .result-icon { font-size: 14px; }
  .result-score {
    font-size: 38px; font-weight: 800;
    color: #0f172a; line-height: 1;
    margin-bottom: 12px;
  }
  .result-score span {
    font-size: 14px; color: #94a3b8; font-weight: 500;
  }
  .result-jurisdictions {
    display: flex; gap: 6px; flex-wrap: wrap;
    margin-bottom: 12px;
  }
  .juris {
    flex: 1 1 60px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    color: var(--c, #0f172a);
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 11px; font-weight: 600;
    text-align: center;
  }
  .juris-error { color: #94a3b8; }
  .result-recs {
    margin: 0 0 12px 0;
    padding: 8px 10px 8px 26px;
    background: #f8fafc;
    border-radius: 6px;
    font-size: 12px; color: #475569;
    line-height: 1.5;
  }
  .result-recs li { margin-bottom: 4px; }
  .result-recs li:last-child { margin-bottom: 0; }
  .result-cta {
    display: block; text-align: center;
    color: #0d9488;
    font-weight: 600; font-size: 13px;
    text-decoration: none;
    padding: 8px 0;
    border-top: 1px solid #f1f5f9;
    margin-top: 4px;
  }
  .result-cta:hover { color: #0f766e; }

  .error {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    padding: 12px;
  }
  .error-msg {
    color: #dc2626; font-size: 13px;
    margin: 0 0 10px 0;
  }
  .error .primary-btn-link { background: #dc2626; }
  .error .primary-btn-link:hover { background: #b91c1c; }
`

// Wire up close button (delegated, since shadow root is created above)
document.addEventListener('click', (e) => {
  const target = e.target as HTMLElement
  if (target.id === 'smp-close') {
    unmount()
  }
})
