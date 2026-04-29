import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'

import { env } from '@/lib/env'

/**
 * Supabase client for Server Components, Route Handlers, and Server Actions.
 *
 * Reads session from cookies on each request. Cookie writes fail silently
 * in Server Components (they're read-only there) — that's expected.
 */
export function createSupabaseServerClient() {
  const cookieStore = cookies()

  return createServerClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_ANON_KEY, {
    cookies: {
      get(name: string) {
        return cookieStore.get(name)?.value
      },
      set(name: string, value: string, options: CookieOptions) {
        try {
          cookieStore.set({ name, value, ...options })
        } catch {
          // Server Components cannot set cookies — ignore silently
        }
      },
      remove(name: string, options: CookieOptions) {
        try {
          cookieStore.set({ name, value: '', ...options })
        } catch {
          // Same as above
        }
      },
    },
  })
}
