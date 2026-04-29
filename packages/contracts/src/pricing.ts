import { z } from 'zod'
import type { ToolId } from './branding'

/**
 * Pricing contracts.
 *
 * All plan definitions, tier limits, and bundle configurations.
 * Consumed by: web pricing page, Lemon Squeezy checkout integration,
 * workers quota enforcement.
 */

// ---------------------------------------------------------------------------
// Plan tiers per tool
// ---------------------------------------------------------------------------

export const PLAN_TIER_SCHEMA = z.enum([
  'free',
  'starter',
  'pro',
  'agency',
  'studio',
  'scale',
  'core_bundle',
  'pro_bundle',
  'empire_bundle',
])
export type PlanTier = z.infer<typeof PLAN_TIER_SCHEMA>

export const BILLING_CYCLE_SCHEMA = z.enum(['monthly', 'annual'])
export type BillingCycle = z.infer<typeof BILLING_CYCLE_SCHEMA>

export const SUBSCRIPTION_STATUS_SCHEMA = z.enum([
  'trialing',
  'active',
  'past_due',
  'cancelled',
  'paused',
  'expired',
])
export type SubscriptionStatus = z.infer<typeof SUBSCRIPTION_STATUS_SCHEMA>

// ---------------------------------------------------------------------------
// Limit definitions — what each tier allows
// ---------------------------------------------------------------------------

export interface ToolLimits {
  readonly [key: string]: number | boolean
}

export const LIMIT_UNLIMITED = -1 as const

// ---------------------------------------------------------------------------
// Individual tool pricing
// ---------------------------------------------------------------------------

export interface PlanConfig {
  readonly price: number
  readonly annualPrice: number
  readonly limits: ToolLimits
}

export const TRADEMARK_SHIELD_PLANS: Record<string, PlanConfig> = {
  free: {
    price: 0,
    annualPrice: 0,
    limits: {
      searches_per_month: 5,
      monitors: 0,
      jurisdictions: 1,
      api_access: false,
      csv_export: false,
    },
  },
  starter: {
    price: 19,
    annualPrice: 171, // 25% off
    limits: {
      searches_per_month: 500,
      monitors: 25,
      jurisdictions: 4,
      api_access: false,
      csv_export: true,
    },
  },
  pro: {
    price: 49,
    annualPrice: 441,
    limits: {
      searches_per_month: LIMIT_UNLIMITED,
      monitors: 500,
      jurisdictions: 4,
      api_access: true,
      csv_export: true,
      bulk_search: true,
    },
  },
  agency: {
    price: 149,
    annualPrice: 1341,
    limits: {
      searches_per_month: LIMIT_UNLIMITED,
      monitors: LIMIT_UNLIMITED,
      jurisdictions: 4,
      api_access: true,
      csv_export: true,
      bulk_search: true,
      team_seats: 10,
      white_label: true,
    },
  },
} as const

// ---------------------------------------------------------------------------
// Bundles — the real pricing play
// ---------------------------------------------------------------------------

export interface BundleConfig {
  readonly id: 'core' | 'pro' | 'empire'
  readonly name: string
  readonly price: number
  readonly annualPrice: number
  readonly tools: readonly ToolId[]
  readonly savingsVsIndividual: number
  readonly description: string
  readonly highlighted: boolean
  readonly features: readonly string[]
}

export const BUNDLES: Record<'core' | 'pro' | 'empire', BundleConfig> = {
  core: {
    id: 'core',
    name: 'Core',
    price: 79,
    annualPrice: 711, // 25% off
    tools: ['trademark_shield', 'niche_radar', 'design_engine'],
    savingsVsIndividual: 42,
    description: 'Discover, design, and ship compliant POD products.',
    highlighted: false,
    features: [
      'Unlimited trademark searches',
      '25 niches tracked daily',
      '200 AI designs per month',
      '3 jurisdictions (US, EU, AU)',
      'Email support',
    ],
  },
  pro: {
    id: 'pro',
    name: 'Pro',
    price: 149,
    annualPrice: 1341,
    tools: ['trademark_shield', 'niche_radar', 'design_engine', 'spy', 'pulse'],
    savingsVsIndividual: 37,
    description: 'Compete like a pro with full intelligence and analytics.',
    highlighted: true,
    features: [
      'Everything in Core',
      '50 competitor shops tracked',
      'Cross-platform analytics',
      'Velocity alerts',
      'Priority support',
      'API access',
    ],
  },
  empire: {
    id: 'empire',
    name: 'Empire',
    price: 399,
    annualPrice: 3591,
    tools: ['trademark_shield', 'niche_radar', 'design_engine', 'spy', 'launchpad', 'pulse'],
    savingsVsIndividual: 41,
    description: 'Run a POD empire on autopilot. Agency-grade with white-label option.',
    highlighted: false,
    features: [
      'Everything in Pro',
      'Multi-platform auto-upload',
      'Unlimited listings per month',
      'Team seats (10)',
      'White-label option',
      'Dedicated success manager',
      'Custom integrations',
    ],
  },
} as const

// ---------------------------------------------------------------------------
// Founding member program
// ---------------------------------------------------------------------------

export const FOUNDING_MEMBER = {
  discountPercent: 40,
  limit: 500,
  isLifetime: true,
  badge: 'Founding Member',
  description: 'First 500 users get 40% off for life. Never expires.',
} as const

// ---------------------------------------------------------------------------
// Plan resolution helpers — used by backend for authorization
// ---------------------------------------------------------------------------

/**
 * Given a bundle ID, returns the set of tool IDs it unlocks.
 */
export function getBundleTools(bundleId: keyof typeof BUNDLES): readonly ToolId[] {
  return BUNDLES[bundleId].tools
}

/**
 * Returns the limit for a specific (tool, tier, limit_key) tuple.
 * Returns LIMIT_UNLIMITED (-1) for unlimited, 0 for no access.
 */
export function getToolLimit(
  tool: 'trademark_shield',
  tier: keyof typeof TRADEMARK_SHIELD_PLANS,
  limitKey: string,
): number | boolean {
  const plan = TRADEMARK_SHIELD_PLANS[tier]
  if (!plan) return 0
  return plan.limits[limitKey] ?? 0
}

export function isUnlimited(limit: number | boolean): boolean {
  return limit === LIMIT_UNLIMITED
}
