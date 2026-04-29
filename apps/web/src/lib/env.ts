/**
 * Typed environment variable access.
 *
 * Next.js only exposes `NEXT_PUBLIC_*` vars to the browser. This file
 * validates them at module load time so missing config fails fast rather
 * than silently at runtime.
 */

import { z } from 'zod'

const publicEnvSchema = z.object({
  NEXT_PUBLIC_APP_URL: z.string().url().default('http://localhost:3000'),
  NEXT_PUBLIC_API_URL: z.string().url().default('http://localhost:8000'),
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
  NEXT_PUBLIC_POSTHOG_KEY: z.string().optional(),
  NEXT_PUBLIC_POSTHOG_HOST: z.string().url().default('https://app.posthog.com'),
  NEXT_PUBLIC_SENTRY_DSN: z.string().optional(),
})

/**
 * Validate and export public env vars.
 * In dev, log clear errors; in prod, throw immediately.
 */
function loadPublicEnv(): z.infer<typeof publicEnvSchema> {
  const parsed = publicEnvSchema.safeParse({
    NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
    NEXT_PUBLIC_POSTHOG_HOST: process.env.NEXT_PUBLIC_POSTHOG_HOST,
    NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN,
  })

  if (!parsed.success) {
    const issues = parsed.error.flatten().fieldErrors
    const missing = Object.keys(issues).join(', ')
    throw new Error(
      `Invalid/missing public environment variables: ${missing}. ` +
        `Check .env.local against .env.example.`,
    )
  }
  return parsed.data
}

export const env = loadPublicEnv()
