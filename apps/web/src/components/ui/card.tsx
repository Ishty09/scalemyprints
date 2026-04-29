import { type HTMLAttributes, forwardRef } from 'react'

import { cn } from '@scalemyprints/utils'

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(function Card(
  { className, ...props },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn('rounded-2xl border border-slate-200 bg-white', className)}
      {...props}
    />
  )
})

export const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  function CardHeader({ className, ...props }, ref) {
    return (
      <div ref={ref} className={cn('border-b border-slate-200 px-6 py-4', className)} {...props} />
    )
  },
)

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  function CardTitle({ className, ...props }, ref) {
    return (
      <h3
        ref={ref}
        className={cn('text-lg font-semibold text-slate-900', className)}
        {...props}
      />
    )
  },
)

export const CardContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  function CardContent({ className, ...props }, ref) {
    return <div ref={ref} className={cn('p-6', className)} {...props} />
  },
)

export const CardFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  function CardFooter({ className, ...props }, ref) {
    return (
      <div
        ref={ref}
        className={cn(
          'flex items-center gap-2 border-t border-slate-200 px-6 py-4',
          className,
        )}
        {...props}
      />
    )
  },
)
