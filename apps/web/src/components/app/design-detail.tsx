'use client'

import {
  AlertTriangle,
  ArrowLeft,
  Download,
  Loader2,
  Trash2,
  Wand2,
} from 'lucide-react'
import Link from 'next/link'
import { useState } from 'react'

import {
  DESIGN_STATUS_LABELS,
  DESIGN_STYLE_LABELS,
  DESIGN_STATUS_TERMINAL,
  type DesignJob,
  type DesignArtifact,
} from '@scalemyprints/contracts'

interface DesignDetailProps {
  job: DesignJob
  onIterate: (extraPrompt: string) => void
  onDelete: () => void
  isIterating?: boolean
  isDeleting?: boolean
}

export function DesignDetail({
  job,
  onIterate,
  onDelete,
  isIterating = false,
  isDeleting = false,
}: DesignDetailProps) {
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(
    job.artifacts[0]?.id ?? null,
  )
  const active =
    job.artifacts.find((a) => a.id === activeArtifactId) ?? job.artifacts[0]

  const isTerminal = (DESIGN_STATUS_TERMINAL as readonly string[]).includes(
    job.status,
  )

  return (
    <div className="space-y-6">
      <Link
        href="/dashboard/design-engine"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to gallery
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-900">
            {job.request.prompt}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {DESIGN_STYLE_LABELS[job.request.style]} ·{' '}
            {DESIGN_STATUS_LABELS[job.status]} ·{' '}
            {new Date(job.created_at).toLocaleString()}
          </p>
        </div>
        <button
          type="button"
          onClick={onDelete}
          disabled={isDeleting}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
          {isDeleting ? 'Deleting...' : 'Delete'}
        </button>
      </header>

      {!isTerminal && (
        <div className="flex items-center gap-3 rounded-xl border border-primary-200 bg-primary-50 p-4 text-sm text-primary-800">
          <Loader2 className="h-5 w-5 animate-spin" aria-hidden="true" />
          <span>{DESIGN_STATUS_LABELS[job.status]}...</span>
        </div>
      )}

      {job.status === 'failed' && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          <AlertTriangle
            className="mt-0.5 h-5 w-5 flex-shrink-0"
            aria-hidden="true"
          />
          <div>
            <div className="font-semibold">Generation failed</div>
            {job.failure_message && (
              <div className="mt-1 text-rose-700">{job.failure_message}</div>
            )}
          </div>
        </div>
      )}

      {active && (
        <DesignViewer
          active={active}
          artifacts={job.artifacts}
          onSelect={setActiveArtifactId}
        />
      )}

      {job.enriched_prompt && (
        <details className="rounded-xl border border-slate-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">
            Refined prompt used
          </summary>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600">
            {job.enriched_prompt}
          </p>
        </details>
      )}

      {isTerminal && job.status === 'completed' && (
        <IteratePanel onIterate={onIterate} isIterating={isIterating} />
      )}
    </div>
  )
}

function DesignViewer({
  active,
  artifacts,
  onSelect,
}: {
  active: DesignArtifact
  artifacts: DesignArtifact[]
  onSelect: (id: string) => void
}) {
  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {active.public_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={active.public_url}
            alt="Generated design"
            className="mx-auto block max-h-[640px] w-full bg-[conic-gradient(at_50%_50%,#f8fafc_25%,#e2e8f0_25%_50%,#f8fafc_50%_75%,#e2e8f0_75%)] bg-[length:24px_24px] object-contain"
          />
        ) : (
          <div className="flex aspect-square items-center justify-center bg-slate-50 text-slate-400">
            <Loader2 className="h-12 w-12 animate-spin" aria-hidden="true" />
          </div>
        )}
        <div className="flex items-center justify-between border-t border-slate-100 p-3 text-xs text-slate-600">
          <span>
            {active.width} × {active.height} · {active.format}
          </span>
          {active.public_url && (
            <a
              href={active.public_url}
              download
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-slate-200 px-2 py-1 font-medium hover:border-primary-300 hover:bg-primary-50 hover:text-primary-700"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Download
            </a>
          )}
        </div>
      </div>

      {artifacts.length > 1 && (
        <div className="flex gap-2 overflow-x-auto" aria-label="Variants">
          {artifacts.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => onSelect(a.id)}
              aria-pressed={a.id === active.id}
              className={`relative flex-shrink-0 overflow-hidden rounded-lg border-2 transition-all ${
                a.id === active.id
                  ? 'border-primary-500'
                  : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              {a.thumbnail_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={a.thumbnail_url}
                  alt=""
                  className="block h-16 w-16 object-cover"
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function IteratePanel({
  onIterate,
  isIterating,
}: {
  onIterate: (extra: string) => void
  isIterating: boolean
}) {
  const [text, setText] = useState('')

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-1 font-display text-base font-semibold text-slate-900">
        Iterate on this design
      </h2>
      <p className="mb-3 text-xs text-slate-500">
        Add an instruction (e.g. &quot;make it more pastel&quot;) to refine the result.
        Counts as a new generation against your quota.
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. softer palette, larger typography"
          maxLength={300}
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
        />
        <button
          type="button"
          onClick={() => {
            if (text.trim().length < 3) return
            onIterate(text.trim())
          }}
          disabled={isIterating || text.trim().length < 3}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isIterating ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Wand2 className="h-4 w-4" aria-hidden="true" />
          )}
          Iterate
        </button>
      </div>
    </section>
  )
}
