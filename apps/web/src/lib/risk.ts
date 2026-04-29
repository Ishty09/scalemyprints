import type { BadgeProps } from '@/components/ui/badge'
import type { RiskLevel } from '@scalemyprints/contracts'

/**
 * Map risk level → Badge variant.
 * Single source of truth for risk presentation across the app.
 */
export function riskBadgeVariant(level: RiskLevel): BadgeProps['variant'] {
  return level
}

export function riskScoreColor(score: number): string {
  if (score <= 20) return 'text-success-600'
  if (score <= 40) return 'text-blue-600'
  if (score <= 60) return 'text-warning-600'
  if (score <= 80) return 'text-accent-600'
  return 'text-danger-600'
}

export function riskBarColor(score: number): string {
  if (score <= 20) return 'bg-success-500'
  if (score <= 40) return 'bg-blue-500'
  if (score <= 60) return 'bg-warning-500'
  if (score <= 80) return 'bg-accent-500'
  return 'bg-danger-500'
}
