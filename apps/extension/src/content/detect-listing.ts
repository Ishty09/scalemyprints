/**
 * Listing page detector.
 *
 * Each platform exposes the listing title in a different DOM element. This
 * module isolates that fragility — if Etsy renames a class, only this file
 * needs to change.
 */

export type Platform = 'etsy' | 'amazon' | 'redbubble'

export interface ListingInfo {
  platform: Platform
  title: string
  /** Best-guess of the Nice classes this listing falls under */
  niceClasses: number[]
}

/**
 * Detect the listing on the current page, or return null if not on a listing.
 * Pure function — no DOM mutations.
 */
export function detectListing(): ListingInfo | null {
  const url = window.location.href
  const detector = pickDetector(url)
  if (!detector) return null
  return detector()
}

function pickDetector(url: string): (() => ListingInfo | null) | null {
  if (url.includes('etsy.com/') && url.includes('/listing/')) return detectEtsy
  if (url.includes('amazon.') && url.includes('/dp/')) return detectAmazon
  if (url.includes('redbubble.com/i/')) return detectRedbubble
  return null
}

// ---------------------------------------------------------------------------
// Etsy
// ---------------------------------------------------------------------------

function detectEtsy(): ListingInfo | null {
  const title = readText([
    'h1[data-buy-box-listing-title]',
    'h1[data-listing-page-title]',
    'h1.wt-text-body-01',
    'h1',
  ])
  if (!title) return null

  return {
    platform: 'etsy',
    title,
    niceClasses: guessClassesFromText(title),
  }
}

// ---------------------------------------------------------------------------
// Amazon
// ---------------------------------------------------------------------------

function detectAmazon(): ListingInfo | null {
  const title = readText(['#productTitle', 'h1#title', 'h1.product-title'])
  if (!title) return null

  return {
    platform: 'amazon',
    title,
    niceClasses: guessClassesFromText(title),
  }
}

// ---------------------------------------------------------------------------
// Redbubble
// ---------------------------------------------------------------------------

function detectRedbubble(): ListingInfo | null {
  const title = readText(['h1[data-test-name="title"]', 'h1.hero-banner-title', 'h1'])
  if (!title) return null

  return {
    platform: 'redbubble',
    title,
    niceClasses: guessClassesFromText(title),
  }
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function readText(selectors: string[]): string | null {
  for (const selector of selectors) {
    const element = document.querySelector(selector)
    const text = element?.textContent?.trim()
    if (text) return text
  }
  return null
}

/**
 * Heuristic mapping from listing title to likely Nice classes.
 *
 * POD listings are usually class 25 (apparel), 21 (drinkware), 16 (paper),
 * or 28 (toys). We default to 25 + 21 since most POD shops cover both.
 */
function guessClassesFromText(text: string): number[] {
  const lower = text.toLowerCase()
  const classes = new Set<number>()

  if (/(t-?shirt|tshirt|hoodie|sweatshirt|tank|tee|apparel|sweater)/.test(lower)) {
    classes.add(25)
  }
  if (/(mug|tumbler|bottle|cup|drinkware)/.test(lower)) {
    classes.add(21)
  }
  if (/(sticker|poster|print|card|notebook|journal)/.test(lower)) {
    classes.add(16)
  }
  if (/(toy|game|puzzle)/.test(lower)) {
    classes.add(28)
  }
  if (/(phone case|phone-case|case for)/.test(lower)) {
    classes.add(9)
  }

  // Default fallback for typical POD storefronts
  if (classes.size === 0) {
    return [25, 21]
  }
  return [...classes]
}
