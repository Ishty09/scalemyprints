'use client'

import { AlertCircle, Image as ImageIcon, Loader2 } from 'lucide-react'
import Link from 'next/link'

import {
  DESIGN_STATUS_LABELS,
  DESIGN_STYLE_LABELS,
  type DesignJobListItem,
} from '@scalemyprints/contracts'

interface DesignGalleryProps {
  jobs: DesignJobListItem[]
  isLoading?: boolean
}

export function DesignGallery({ jobs, isLoading }: DesignGalleryProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="aspect-square animate-pulse rounded-xl border border-slate-200 bg-slate-100"
          />
        ))}
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <section className="rounded-xl border border-dashed border-slate-200 bg-white/50 p-8 text-center">
        <ImageIcon className="mx-auto mb-3 h-10 w-10 text-slate-300" aria-hidden="true" />
        <h2 className="mb-1 font-display text-lg font-semibold text-slate-700">
          No designs yet
        </h2>
        <p className="mx-auto max-w-md text-sm text-slate-500">
          Generate your first design above. Each one is saved to your private library.
        </p>
      </section>
    )
  }

  return (
    <ul
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4"
      aria-label="Design history"
    >
      {jobs.map((job) => (
        <li key={job.id}>
          <Link
            href={`/dashboard/design-engine/${job.id}`}
            className="group block overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition-all hover:border-primary-300 hover:shadow-md"
          >
            <DesignTile job={job} />
            <div className="border-t border-slate-100 p-2.5">
              <p className="line-clamp-2 text-xs font-medium text-slate-700">
                {job.prompt}
              </p>
              <div className="mt-1 flex items-center gap-1.5 text-2xs text-slate-500">
                <span>{DESIGN_STYLE_LABELS[job.style]}</span>
                <span className="opacity-40">•</span>
                <span>{DESIGN_STATUS_LABELS[job.status]}</span>
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ul>
  )
}

function DesignTile({ job }: { job: DesignJobListItem }) {
  if (job.status === 'failed') {
    return (
      <div className="flex aspect-square items-center justify-center bg-rose-50 text-rose-500">
        <AlertCircle className="h-8 w-8" aria-hidden="true" />
      </div>
    )
  }

  if (job.thumbnail_url && job.status === 'completed') {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={job.thumbnail_url}
        alt={job.prompt}
        className="aspect-square w-full bg-[conic-gradient(at_50%_50%,#f8fafc_25%,#e2e8f0_25%_50%,#f8fafc_50%_75%,#e2e8f0_75%)] bg-[length:16px_16px] object-contain"
        loading="lazy"
      />
    )
  }

  return (
    <div className="flex aspect-square items-center justify-center bg-slate-50 text-slate-400">
      <Loader2 className="h-8 w-8 animate-spin" aria-hidden="true" />
    </div>
  )
}
