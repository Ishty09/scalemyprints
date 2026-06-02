'use client'

import { Sparkles } from 'lucide-react'

import {
  DESIGN_QUOTA_UNLIMITED,
  isDesignQuotaUnlimited,
  type DesignQuota,
} from '@scalemyprints/contracts'

interface DesignQuotaBadgeProps {
  quota: DesignQuota | undefined
  isLoading?: boolean
}

export function DesignQuotaBadge({ quota, isLoading }: DesignQuotaBadgeProps) {
  if (isLoading || !quota) {
    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Loading quota...</span>
      </div>
    )
  }

  const unlimited = isDesignQuotaUnlimited(quota.monthly_limit)
  const remaining = unlimited ? DESIGN_QUOTA_UNLIMITED : quota.remaining
  const limit = quota.monthly_limit
  const percentUsed =
    unlimited || limit === 0 ? 0 : Math.min(100, (quota.used / limit) * 100)

  const tone =
    unlimited
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : remaining === 0
        ? 'border-rose-200 bg-rose-50 text-rose-700'
        : remaining <= Math.max(1, Math.floor(limit * 0.1))
          ? 'border-amber-200 bg-amber-50 text-amber-700'
          : 'border-slate-200 bg-white text-slate-700'

  return (
    <div
      className={`inline-flex flex-col gap-1 rounded-xl border px-3 py-2 text-xs ${tone}`}
      aria-label="Design quota status"
    >
      <div className="flex items-center gap-2 font-medium">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        {unlimited ? (
          <span>Unlimited designs · {quota.plan}</span>
        ) : (
          <span>
            {quota.used} / {limit} this month · {quota.plan}
          </span>
        )}
      </div>
      {!unlimited && (
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(percentUsed)}
        >
          <div
            className="h-full bg-current opacity-60 transition-all"
            style={{ width: `${percentUsed}%` }}
          />
        </div>
      )}
    </div>
  )
}
