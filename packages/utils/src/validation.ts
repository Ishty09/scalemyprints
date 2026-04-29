/**
 * Validation utilities — lightweight, platform-agnostic.
 * For complex schemas, use Zod from @scalemyprints/contracts.
 */

const EMAIL_REGEX =
  /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/

export function isValidEmail(email: string): boolean {
  return EMAIL_REGEX.test(email) && email.length <= 254
}

export function isValidUrl(urlString: string): boolean {
  try {
    const url = new URL(urlString)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

export function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

export function normalizeString(input: string): string {
  return input.trim().replace(/\s+/g, ' ')
}

/**
 * Check if a phrase is suitable for trademark searching.
 */
export function isValidTrademarkPhrase(phrase: string): {
  valid: boolean
  reason?: string
} {
  const normalized = phrase.trim()

  if (normalized.length === 0) {
    return { valid: false, reason: 'Phrase cannot be empty' }
  }
  if (normalized.length > 200) {
    return { valid: false, reason: 'Phrase too long (max 200 characters)' }
  }
  if (normalized.length < 2) {
    return { valid: false, reason: 'Phrase too short (min 2 characters)' }
  }
  // Allow letters, numbers, common punctuation, and unicode
  if (!/^[\p{L}\p{N}\s.,!?'"&+\-/]+$/u.test(normalized)) {
    return { valid: false, reason: 'Phrase contains invalid characters' }
  }

  return { valid: true }
}
