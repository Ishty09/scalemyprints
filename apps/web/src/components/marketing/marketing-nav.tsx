'use client'

import Link from 'next/link'
import { Menu, X } from 'lucide-react'
import { useState } from 'react'

import { BRAND } from '@scalemyprints/contracts'

const NAV_LINKS = [
  { href: '/trademark-shield', label: 'Trademark Shield' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/about', label: 'About' },
] as const

export function MarketingNav() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2" aria-label={`${BRAND.name} home`}>
            <span className="rounded-md bg-gradient-to-br from-primary-600 to-accent-500 px-2 py-1 font-display text-sm font-bold text-white">
              SMP
            </span>
            <span className="font-semibold text-slate-900">{BRAND.name}</span>
          </Link>

          <nav className="hidden items-center gap-8 md:flex" aria-label="Primary">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-slate-600 transition-colors hover:text-slate-900"
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="hidden items-center gap-3 md:flex">
            <Link
              href="/login"
              className="text-sm font-medium text-slate-700 transition-colors hover:text-slate-900"
            >
              Log in
            </Link>
            <Link
              href="/signup"
              className="inline-flex h-10 items-center justify-center rounded-lg bg-primary-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-primary-700"
            >
              Start free
            </Link>
          </div>

          <button
            type="button"
            className="rounded-md p-2 hover:bg-slate-100 md:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {mobileOpen && (
          <nav className="border-t border-slate-200 py-4 md:hidden" aria-label="Mobile primary">
            <div className="flex flex-col gap-3">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="rounded-md px-2 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  onClick={() => setMobileOpen(false)}
                >
                  {link.label}
                </Link>
              ))}
              <div className="mt-2 flex flex-col gap-2 border-t border-slate-200 pt-3">
                <Link
                  href="/login"
                  className="rounded-md px-2 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Log in
                </Link>
                <Link
                  href="/signup"
                  className="rounded-md bg-primary-600 px-4 py-2 text-center text-sm font-semibold text-white hover:bg-primary-700"
                >
                  Start free
                </Link>
              </div>
            </div>
          </nav>
        )}
      </div>
    </header>
  )
}
