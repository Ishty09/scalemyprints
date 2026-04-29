import Link from 'next/link'
import { ArrowRight, type LucideIcon } from 'lucide-react'

import { Badge } from '@/components/ui'
import type { Tool } from '@scalemyprints/contracts'

interface ToolCardProps {
  tool: Tool
  Icon: LucideIcon
}

export function ToolCard({ tool, Icon }: ToolCardProps) {
  const isLive = tool.status === 'live'

  return (
    <Link
      href={isLive ? `/${tool.slug}` : `/${tool.slug}`}
      className="group block rounded-2xl border border-slate-200 bg-white p-6 transition-all duration-200 hover:border-primary-300 hover:shadow-lg"
    >
      <div className="mb-4 flex items-start justify-between">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary-100 text-primary-600 transition-colors group-hover:bg-primary-600 group-hover:text-white">
          <Icon className="h-6 w-6" aria-hidden="true" />
        </div>
        {isLive ? (
          <Badge variant="safe">Live</Badge>
        ) : (
          <Badge variant="warning">Coming soon</Badge>
        )}
      </div>

      <h3 className="text-xl font-semibold text-slate-900">{tool.name}</h3>
      <p className="mt-1 text-sm font-medium text-primary-600">{tool.tagline}</p>
      <p className="mt-2 text-sm text-slate-600">{tool.description}</p>

      <div className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-900 group-hover:text-primary-600">
        Learn more
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
      </div>
    </Link>
  )
}
