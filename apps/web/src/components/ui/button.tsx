import { forwardRef, type ButtonHTMLAttributes } from 'react'

import { cn } from '@scalemyprints/utils'

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  isLoading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const baseClasses =
  'inline-flex items-center justify-center gap-2 font-semibold rounded-lg ' +
  'transition-colors focus-visible:outline-none focus-visible:ring-2 ' +
  'focus-visible:ring-primary-600 focus-visible:ring-offset-2 ' +
  'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none'

const variantClasses: Record<ButtonVariant, string> = {
  primary: 'bg-primary-600 hover:bg-primary-700 text-white',
  secondary: 'bg-slate-900 hover:bg-slate-800 text-white',
  outline: 'border border-slate-300 hover:bg-slate-50 text-slate-900',
  ghost: 'hover:bg-slate-100 text-slate-700',
  danger: 'bg-danger-500 hover:bg-danger-600 text-white',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = 'primary',
      size = 'md',
      isLoading = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      className,
      type = 'button',
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || isLoading}
        className={cn(baseClasses, variantClasses[variant], sizeClasses[size], className)}
        aria-busy={isLoading || undefined}
        {...props}
      >
        {isLoading ? (
          <Spinner />
        ) : (
          <>
            {leftIcon}
            {children}
            {rightIcon}
          </>
        )}
      </button>
    )
  },
)

function Spinner() {
  return (
    <svg
      className="h-4 w-4 animate-spin"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  )
}
