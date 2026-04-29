import { z } from 'zod'
import { PLAN_TIER_SCHEMA, SUBSCRIPTION_STATUS_SCHEMA } from './pricing'

/**
 * Authentication & user contracts.
 */

// ---------------------------------------------------------------------------
// User roles
// ---------------------------------------------------------------------------

export const USER_ROLE_SCHEMA = z.enum(['user', 'admin', 'agency_owner', 'agency_member'])
export type UserRole = z.infer<typeof USER_ROLE_SCHEMA>

// ---------------------------------------------------------------------------
// User profile
// ---------------------------------------------------------------------------

export const USER_PROFILE_SCHEMA = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  full_name: z.string().nullable(),
  avatar_url: z.string().url().nullable(),
  timezone: z.string().default('UTC'),
  locale: z.string().default('en-US'),
  is_founding_member: z.boolean().default(false),
  onboarding_completed: z.boolean().default(false),
  role: USER_ROLE_SCHEMA.default('user'),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
})
export type UserProfile = z.infer<typeof USER_PROFILE_SCHEMA>

// ---------------------------------------------------------------------------
// Subscription (derived from Lemon Squeezy or free tier)
// ---------------------------------------------------------------------------

export const SUBSCRIPTION_SCHEMA = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  plan_tier: PLAN_TIER_SCHEMA,
  status: SUBSCRIPTION_STATUS_SCHEMA,
  active_tools: z.record(z.boolean()),
  is_annual: z.boolean().default(false),
  trial_ends_at: z.string().datetime().nullable(),
  current_period_end: z.string().datetime().nullable(),
  cancel_at_period_end: z.boolean().default(false),
})
export type Subscription = z.infer<typeof SUBSCRIPTION_SCHEMA>

// ---------------------------------------------------------------------------
// Current user — what the frontend gets from /api/me
// ---------------------------------------------------------------------------

export interface CurrentUser {
  readonly profile: UserProfile
  readonly subscription: Subscription
  readonly entitlements: Entitlements
}

export interface Entitlements {
  readonly tools: Record<string, boolean>
  readonly limits: Record<string, Record<string, number | boolean>>
}

// ---------------------------------------------------------------------------
// Signup / Login request schemas
// ---------------------------------------------------------------------------

export const SIGNUP_REQUEST_SCHEMA = z.object({
  email: z.string().email('Please enter a valid email'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  full_name: z.string().min(1, 'Name is required').max(100).optional(),
  referral_code: z.string().optional(),
  marketing_opt_in: z.boolean().default(false),
})
export type SignupRequest = z.infer<typeof SIGNUP_REQUEST_SCHEMA>

export const LOGIN_REQUEST_SCHEMA = z.object({
  email: z.string().email(),
  password: z.string().min(1),
})
export type LoginRequest = z.infer<typeof LOGIN_REQUEST_SCHEMA>

// ---------------------------------------------------------------------------
// Waitlist (pre-launch)
// ---------------------------------------------------------------------------

export const WAITLIST_SIGNUP_REQUEST_SCHEMA = z.object({
  email: z.string().email('Please enter a valid email'),
  name: z.string().max(100).optional(),
  source: z.string().max(50).optional(),
  referrer: z.string().max(200).optional(),
  interested_tools: z.array(z.string()).optional(),
})
export type WaitlistSignupRequest = z.infer<typeof WAITLIST_SIGNUP_REQUEST_SCHEMA>

export interface WaitlistSignupResponse {
  readonly position: number
  readonly total_signups: number
  readonly estimated_access_days: number
}
