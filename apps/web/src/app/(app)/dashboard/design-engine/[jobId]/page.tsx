'use client'

import { Loader2 } from 'lucide-react'
import { useParams, useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type { DesignGenerateBody } from '@scalemyprints/contracts'

import { DesignDetail } from '@/components/app/design-detail'
import {
  useDeleteDesignJob,
  useDesignJob,
  useIterateDesign,
} from '@/hooks/use-design'
import { ApiClientError } from '@/lib/api-client'

export default function DesignJobPage() {
  const params = useParams<{ jobId: string }>()
  const router = useRouter()
  const jobId = params?.jobId

  const job = useDesignJob(jobId)
  const iterate = useIterateDesign(jobId ?? '')
  const del = useDeleteDesignJob()

  function handleIterate(extraPrompt: string) {
    if (!job.data) return
    const body: DesignGenerateBody = {
      prompt: `${job.data.request.prompt}. ${extraPrompt}`,
      style: job.data.request.style,
      aspect: job.data.request.aspect,
      output_format: job.data.request.output_format,
      variant_count: job.data.request.variant_count,
      negative_prompt: job.data.request.negative_prompt,
    }
    iterate.mutate(body, {
      onSuccess: (newJob) => {
        if (newJob.status === 'failed') {
          toast.error(newJob.failure_message ?? 'Iteration failed.')
          return
        }
        toast.success('New variant generated.')
        router.push(`/dashboard/design-engine/${newJob.id}`)
      },
      onError: (error) => {
        if (error instanceof ApiClientError && error.code === 'quota_exceeded') {
          toast.error('Monthly limit reached. Upgrade to continue.')
          return
        }
        toast.error('Could not iterate. Please try again.')
      },
    })
  }

  function handleDelete() {
    if (!jobId) return
    if (
      typeof window !== 'undefined' &&
      !window.confirm('Delete this design? This cannot be undone.')
    ) {
      return
    }
    del.mutate(jobId, {
      onSuccess: () => {
        toast.success('Design deleted.')
        router.push('/dashboard/design-engine')
      },
      onError: () => {
        toast.error('Could not delete design.')
      },
    })
  }

  if (job.isLoading) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-4xl items-center justify-center px-6 py-8 text-slate-500">
        <Loader2 className="h-6 w-6 animate-spin" aria-hidden="true" />
      </div>
    )
  }

  if (job.isError || !job.data) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-rose-800">
          <h1 className="mb-1 font-display text-lg font-semibold">
            Design not found
          </h1>
          <p className="text-sm">
            This design may have been deleted, or it doesn&apos;t belong to your
            account.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <DesignDetail
        job={job.data}
        onIterate={handleIterate}
        onDelete={handleDelete}
        isIterating={iterate.isPending}
        isDeleting={del.isPending}
      />
    </div>
  )
}
