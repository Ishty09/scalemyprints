'use client'

import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  ExternalLink,
  Info,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'

import {
  JURISDICTION_NAMES,
  RISK_LEVEL_LABELS,
  type JurisdictionRisk,
  type RiskLevel,
  type TrademarkRecommendation,
  type TrademarkRecord,
  type TrademarkSearchResponse,
} from '@scalemyprints/contracts'
import { cn } from '@scalemyprints/utils'

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { riskBadgeVariant, riskBarColor, riskScoreColor } from '@/lib/risk'

interface TrademarkResultsProps {
  result: TrademarkSearchResponse
}

export function TrademarkResults({ result }: TrademarkResultsProps) {
  return (
    <div className="space-y-6">
      <OverallRiskCard result={result} />
      {result.recommendations.length > 0 && (
        <RecommendationsCard recommendations={result.recommendations} />
      )}
      <JurisdictionsCard jurisdictions={result.jurisdictions} />
    </div>
  )
}

function OverallRiskCard({ result }: { result: TrademarkSearchResponse }) {
  const Icon = riskIcon(result.overall_risk_level)
  const variant = riskBadgeVariant(result.overall_risk_level)

  return (
    <Card>
      <CardContent className="p-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className={cn('flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100', riskScoreColor(result.overall_risk_score))}>
              <Icon className="h-8 w-8" aria-hidden="true" />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                Overall risk
              </div>
              <div className="mt-1 flex items-center gap-3">
                <span className="text-2xl font-bold text-slate-900">
                  {RISK_LEVEL_LABELS[result.overall_risk_level]}
                </span>
                <Badge variant={variant}>{result.overall_risk_level}</Badge>
              </div>
            </div>
          </div>

          <div className="text-right">
            <div className={cn('text-5xl font-bold', riskScoreColor(result.overall_risk_score))}>
              {result.overall_risk_score}
            </div>
            <div className="text-sm text-slate-500">out of 100</div>
          </div>
        </div>

        <div className="mt-6">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={cn('h-full rounded-full transition-all', riskBarColor(result.overall_risk_score))}
              style={{ width: `${result.overall_risk_score}%` }}
              role="progressbar"
              aria-valuenow={result.overall_risk_score}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
          <span>
            Phrase: <span className="font-medium text-slate-700">{result.phrase}</span>
          </span>
          {result.from_cache && (
            <span className="text-primary-600">⚡ Cached result</span>
          )}
          <span>Analyzed in {result.duration_ms}ms</span>
        </div>
      </CardContent>
    </Card>
  )
}

function RecommendationsCard({
  recommendations,
}: {
  recommendations: TrademarkRecommendation[]
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>💡 Recommendations</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {recommendations.map((rec, index) => (
          <RecommendationRow key={index} recommendation={rec} />
        ))}
      </CardContent>
    </Card>
  )
}

function RecommendationRow({
  recommendation,
}: {
  recommendation: TrademarkRecommendation
}) {
  const colors = {
    success: 'bg-success-50 text-success-600 border-green-200',
    info: 'bg-primary-50 text-primary-700 border-primary-200',
    warning: 'bg-warning-50 text-warning-600 border-amber-200',
    danger: 'bg-danger-50 text-danger-600 border-red-200',
  }
  const Icon = {
    success: CheckCircle,
    info: Info,
    warning: AlertTriangle,
    danger: XCircle,
  }[recommendation.severity]

  return (
    <div className={cn('rounded-lg border p-3', colors[recommendation.severity])}>
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
        <div className="flex-1">
          <p className="text-sm font-medium">{recommendation.message}</p>
          {recommendation.action && (
            <p className="mt-1 text-xs opacity-90">{recommendation.action}</p>
          )}
        </div>
      </div>
    </div>
  )
}

function JurisdictionsCard({ jurisdictions }: { jurisdictions: JurisdictionRisk[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>🌍 Jurisdiction breakdown</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {jurisdictions.map((jurisdiction) => (
          <JurisdictionRow key={jurisdiction.code} jurisdiction={jurisdiction} />
        ))}
      </CardContent>
    </Card>
  )
}

function JurisdictionRow({ jurisdiction }: { jurisdiction: JurisdictionRisk }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = jurisdiction.matching_records.length > 0
  const variant = riskBadgeVariant(jurisdiction.risk_level)

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        disabled={!hasDetails}
        className={cn(
          'flex w-full items-center justify-between p-4 text-left',
          hasDetails ? 'hover:bg-slate-50' : 'cursor-default',
        )}
        aria-expanded={hasDetails ? expanded : undefined}
      >
        <div className="flex items-center gap-4">
          <span className="font-display text-2xl font-bold text-slate-900">
            {jurisdiction.code}
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className={cn('text-sm font-semibold', riskScoreColor(jurisdiction.risk_score))}>
                {jurisdiction.risk_score}/100
              </span>
              <Badge variant={variant}>{jurisdiction.risk_level}</Badge>
            </div>
            <div className="mt-0.5 text-xs text-slate-500">
              {JURISDICTION_NAMES[jurisdiction.code]}
              {jurisdiction.error ? (
                <span className="ml-2 text-warning-600">· {jurisdiction.error}</span>
              ) : (
                <>
                  {' · '}
                  {jurisdiction.active_registrations} active
                  {' · '}
                  {jurisdiction.pending_applications} pending
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {jurisdiction.arbitrage_available && (
            <Badge variant="safe">✓ Safe to sell here</Badge>
          )}
          {hasDetails && (
            <ChevronDown
              className={cn(
                'h-4 w-4 text-slate-400 transition-transform',
                expanded && 'rotate-180',
              )}
              aria-hidden="true"
            />
          )}
        </div>
      </button>

      {expanded && hasDetails && (
        <div className="border-t border-slate-200 bg-slate-50 p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-700">
            Matching records ({jurisdiction.matching_records.length})
          </div>
          <div className="space-y-2">
            {jurisdiction.matching_records.slice(0, 5).map((record) => (
              <RecordRow key={record.registration_number} record={record} />
            ))}
            {jurisdiction.matching_records.length > 5 && (
              <p className="text-xs text-slate-500">
                + {jurisdiction.matching_records.length - 5} more records
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function RecordRow({ record }: { record: TrademarkRecord }) {
  return (
    <div className="rounded-md bg-white p-3 text-xs">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="truncate font-medium text-slate-900">{record.mark}</div>
          <div className="mt-0.5 truncate text-slate-600">
            {record.owner ?? 'Unknown owner'} · {record.status} · Class {record.nice_class ?? '?'}
          </div>
        </div>
        {record.source_url && (
          <a
            href={record.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex flex-shrink-0 items-center gap-1 text-primary-600 hover:underline"
          >
            View <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        )}
      </div>
    </div>
  )
}

function riskIcon(level: RiskLevel) {
  switch (level) {
    case 'safe':
    case 'low':
      return CheckCircle
    case 'medium':
      return Info
    case 'high':
      return AlertTriangle
    case 'critical':
      return XCircle
  }
}
