import { type HTMLAttributes, forwardRef } from 'react'

import { cn } from '@scalemyprints/utils'

type BadgeVariant = 'default' | 'safe' | 'low' | 'medium' | 'high' | 'critical' | 'info' | 'warning'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

const variantClasses: Record<BadgeVariant, string> = {
  default: 'bg-slate-100 text-slate-700 border-slate-200',
  safe: 'bg-success-50 text-success-600 border-green-200',
  low: 'bg-blue-50 text-blue-700 border-blue-200',
  medium: 'bg-warning-50 text-warning-600 border-amber-200',
  high: 'bg-accent-50 text-accent-600 border-orange-200',
  critical: 'bg-danger-50 text-danger-600 border-red-200',
  info: 'bg-primary-50 text-primary-700 border-primary-200',
  warning: 'bg-warning-50 text-warning-600 border-amber-200',
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { variant = 'default', className, children, ...props },
  ref,
) {
  return (
    <span
      ref={ref}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5',
        'text-xs font-semibold',
        variantClasses[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
})
