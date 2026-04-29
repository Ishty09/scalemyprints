import { createBrowserClient } from '@supabase/ssr'

import { env } from '@/lib/env'

/**
 * Supabase client for use in Client Components.
 *
 * Uses cookie-based sessions so SSR + CSR stay in sync.
 */
export function createSupabaseBrowserClient() {
  return createBrowserClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_ANON_KEY)
}
