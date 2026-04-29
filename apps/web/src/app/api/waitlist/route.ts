import { NextRequest, NextResponse } from 'next/server'
import { z } from 'zod'

import {
  WAITLIST_SIGNUP_REQUEST_SCHEMA,
  buildFailure,
  buildSuccess,
  type WaitlistSignupResponse,
} from '@scalemyprints/contracts'

import { createSupabaseServerClient } from '@/lib/supabase/server'

export async function POST(request: NextRequest) {
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json(
      buildFailure('invalid_input', 'Request body must be valid JSON'),
      { status: 400 },
    )
  }

  const parsed = WAITLIST_SIGNUP_REQUEST_SCHEMA.safeParse(body)
  if (!parsed.success) {
    return NextResponse.json(
      buildFailure('validation_error', 'Invalid waitlist signup', {
        errors: parsed.error.flatten().fieldErrors,
      }),
      { status: 400 },
    )
  }

  const supabase = createSupabaseServerClient()

  const { data, error } = await supabase
    .from('waitlist')
    .insert({
      email: parsed.data.email,
      name: parsed.data.name ?? null,
      source: parsed.data.source ?? 'web',
      referrer: parsed.data.referrer ?? null,
      interested_tools: parsed.data.interested_tools ?? null,
    })
    .select('id')
    .single()

  if (error) {
    // Unique violation = already on the list (idempotent success)
    if (error.code === '23505') {
      return NextResponse.json(
        buildSuccess<WaitlistSignupResponse>({
          position: 0,
          total_signups: 0,
          estimated_access_days: 0,
        }),
      )
    }
    return NextResponse.json(buildFailure('internal_error', 'Could not save signup'), {
      status: 500,
    })
  }

  // Get position (count of signups created at or before this one)
  const { count } = await supabase
    .from('waitlist')
    .select('*', { count: 'exact', head: true })

  const position = count ?? 0

  return NextResponse.json(
    buildSuccess<WaitlistSignupResponse>({
      position,
      total_signups: position,
      estimated_access_days: Math.max(7, Math.ceil(position / 50) * 7),
    }),
  )
}
