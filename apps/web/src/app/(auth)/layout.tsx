import Link from 'next/link'
import type { ReactNode } from 'react'

import { BRAND } from '@scalemyprints/contracts'

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-6 py-12">
      <Link href="/" className="mb-8 flex items-center gap-2">
        <span className="rounded-md bg-gradient-to-br from-primary-600 to-accent-500 px-2 py-1 font-display text-sm font-bold text-white">
          SMP
        </span>
        <span className="font-semibold text-slate-900">{BRAND.name}</span>
      </Link>
      <div className="w-full max-w-md">{children}</div>
    </div>
  )
}
