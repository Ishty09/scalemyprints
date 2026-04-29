import type { NextRequest } from 'next/server'

import { updateSupabaseSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return updateSupabaseSession(request)
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - images (public images)
     */
    '/((?!_next/static|_next/image|favicon.ico|images/).*)',
  ],
}
