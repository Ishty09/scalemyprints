import { NextResponse } from 'next/server'

import { createSupabaseServerClient } from '@/lib/supabase/server'

export async function POST() {
  const supabase = createSupabaseServerClient()
  await supabase.auth.signOut()
  return NextResponse.redirect(new URL('/', process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'), { status: 303 })
}
