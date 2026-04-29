import { forwardRef, type InputHTMLAttributes } from 'react'

import { cn } from '@scalemyprints/utils'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, error, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        'h-10 w-full rounded-lg border bg-white px-3 text-sm text-slate-900',
        'placeholder:text-slate-400 transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-offset-1',
        'disabled:cursor-not-allowed disabled:opacity-50',
        error
          ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500'
          : 'border-slate-300 focus:border-primary-600 focus:ring-primary-600',
        className,
      )}
      aria-invalid={error || undefined}
      {...props}
    />
  )
})
