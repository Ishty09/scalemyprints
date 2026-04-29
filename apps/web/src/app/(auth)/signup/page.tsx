'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'

import { SIGNUP_REQUEST_SCHEMA } from '@scalemyprints/contracts'

import { Button, Card, CardContent, Input } from '@/components/ui'
import { createSupabaseBrowserClient } from '@/lib/supabase/client'

export default function SignupPage() {
  const router = useRouter()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErrors({})

    const parsed = SIGNUP_REQUEST_SCHEMA.safeParse({
      email,
      password,
      full_name: fullName || undefined,
      marketing_opt_in: false,
    })
    if (!parsed.success) {
      const fieldErrors = parsed.error.flatten().fieldErrors
      setErrors({
        email: fieldErrors.email?.[0] ?? '',
        password: fieldErrors.password?.[0] ?? '',
        full_name: fieldErrors.full_name?.[0] ?? '',
      })
      return
    }

    setIsSubmitting(true)
    try {
      const supabase = createSupabaseBrowserClient()
      const { error } = await supabase.auth.signUp({
        email: parsed.data.email,
        password: parsed.data.password,
        options: {
          data: parsed.data.full_name ? { full_name: parsed.data.full_name } : undefined,
        },
      })
      if (error) {
        toast.error(error.message ?? 'Signup failed')
        return
      }
      toast.success('Check your email to confirm your account.')
      router.push('/login')
    } catch {
      toast.error('Something went wrong. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardContent className="p-8">
        <h1 className="font-display text-2xl font-bold text-slate-900">Create your account</h1>
        <p className="mt-1 text-sm text-slate-600">
          Free forever — 5 trademark searches per month, no credit card required.
        </p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="full_name" className="mb-1.5 block text-sm font-medium text-slate-700">
              Name <span className="text-slate-400">(optional)</span>
            </label>
            <Input
              id="full_name"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              error={Boolean(errors.full_name)}
            />
          </div>

          <div>
            <label htmlFor="email" className="mb-1.5 block text-sm font-medium text-slate-700">
              Email
            </label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={Boolean(errors.email)}
            />
            {errors.email && <p className="mt-1 text-xs text-danger-600">{errors.email}</p>}
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-sm font-medium text-slate-700">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={Boolean(errors.password)}
            />
            {errors.password ? (
              <p className="mt-1 text-xs text-danger-600">{errors.password}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-500">At least 8 characters.</p>
            )}
          </div>

          <Button type="submit" size="lg" isLoading={isSubmitting} className="w-full">
            Create account
          </Button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">
          By signing up, you agree to our{' '}
          <Link href="/terms" className="hover:text-slate-700">
            Terms
          </Link>{' '}
          and{' '}
          <Link href="/privacy" className="hover:text-slate-700">
            Privacy Policy
          </Link>
          .
        </p>

        <p className="mt-6 text-center text-sm text-slate-600">
          Already have an account?{' '}
          <Link href="/login" className="font-semibold text-primary-600 hover:text-primary-700">
            Log in
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}
