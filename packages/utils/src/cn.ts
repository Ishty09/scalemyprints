import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merge Tailwind classes with proper conflict resolution.
 * Combines clsx (conditional logic) with tailwind-merge (resolves conflicts).
 *
 * @example
 *   cn('px-2 py-1', isActive && 'bg-primary-600', className)
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
