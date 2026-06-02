'use client'

import { Sparkles } from 'lucide-react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type { DesignGenerateBody } from '@scalemyprints/contracts'

import { DesignGallery } from '@/components/app/design-gallery'
import { DesignPromptForm } from '@/components/app/design-prompt-form'
import { DesignQuotaBadge } from '@/components/app/design-quota-badge'
import {
  useDesignJobs,
  useDesignQuota,
  useDesignStyles,
  useGenerateDesign,
} from '@/hooks/use-design'
import { ApiClientError } from '@/lib/api-client'

export default function DesignEnginePage() {
  const router = useRouter()
  const generate = useGenerateDesign()
  const quota = useDesignQuota()
  const styles = useDesignStyles()
  const jobs = useDesignJobs({ limit: 20 })

  const quotaReached =
    quota.data !== undefined &&
    quota.data.monthly_limit !== -1 &&
    quota.data.remaining <= 0

  function handleSubmit(body: DesignGenerateBody) {
    generate.mutate(body, {
      onSuccess: (job) => {
        if (job.status === 'failed') {
          toast.error(
            job.failure_message ?? 'Design generation failed. Please try again.',
          )
          return
        }
        toast.success('Design generated.')
        router.push(`/dashboard/design-engine/${job.id}`)
      },
      onError: (error) => {
        if (error instanceof ApiClientError) {
          if (error.code === 'quota_exceeded') {
            toast.error('Monthly limit reached. Upgrade to continue.')
            return
          }
          if (error.code === 'policy_violation') {
            toast.error('Prompt violates the content policy. Please rephrase.')
            return
          }
          if (error.code === 'rate_limited') {
            toast.error('Too many requests. Wait a minute and try again.')
            return
          }
          if (
            error.code === 'provider_unavailable' ||
            error.code === 'provider_rate_limited'
          ) {
            toast.error('Image generation is temporarily unavailable.')
            return
          }
        }
        toast.error('Could not generate design. Please try again.')
      },
    })
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Sparkles className="h-7 w-7 text-primary-600" aria-hidden="true" />
            <h1 className="font-display text-3xl font-bold text-slate-900">
              Design Engine
            </h1>
          </div>
          <DesignQuotaBadge quota={quota.data} isLoading={quota.isLoading} />
        </div>
        <p className="text-slate-600">
          Generate print-ready designs with multi-model orchestration. Style
          consistency, transparent backgrounds, full provenance.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <section aria-label="Generate design">
          <DesignPromptForm
            onSubmit={handleSubmit}
            isLoading={generate.isPending}
            styles={styles.data}
            quotaReached={quotaReached}
          />
          {quotaReached && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              You&apos;ve used all {quota.data?.monthly_limit} designs this month.{' '}
              <Link
                href="/pricing"
                className="font-semibold text-amber-900 underline underline-offset-2 hover:no-underline"
              >
                Upgrade your plan
              </Link>{' '}
              to keep going.
            </div>
          )}
        </section>

        <section aria-label="Design history">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            Recent designs
          </h2>
          <DesignGallery jobs={jobs.data?.jobs ?? []} isLoading={jobs.isLoading} />
        </section>
      </div>
    </div>
  )
}
