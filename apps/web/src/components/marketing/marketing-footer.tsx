import Link from 'next/link'

import { BRAND } from '@scalemyprints/contracts'

const FOOTER_SECTIONS = [
  {
    title: 'Product',
    links: [
      { href: '/trademark-shield', label: 'Trademark Shield' },
      { href: '/pricing', label: 'Pricing' },
      { href: '/changelog', label: 'Changelog' },
    ],
  },
  {
    title: 'Company',
    links: [
      { href: '/about', label: 'About' },
      { href: '/blog', label: 'Blog' },
      { href: '/contact', label: 'Contact' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { href: '/terms', label: 'Terms of Service' },
      { href: '/privacy', label: 'Privacy Policy' },
      { href: '/dmca', label: 'DMCA' },
    ],
  },
] as const

export function MarketingFooter() {
  const year = new Date().getFullYear()

  return (
    <footer className="mt-20 border-t border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-7xl px-6 py-12">
        <div className="grid grid-cols-2 gap-8 md:grid-cols-4">
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2" aria-label={`${BRAND.name} home`}>
              <span className="rounded-md bg-gradient-to-br from-primary-600 to-accent-500 px-2 py-1 font-display text-sm font-bold text-white">
                SMP
              </span>
              <span className="font-semibold text-slate-900">{BRAND.name}</span>
            </Link>
            <p className="mt-3 max-w-xs text-sm text-slate-600">{BRAND.tagline}</p>
          </div>

          {FOOTER_SECTIONS.map((section) => (
            <div key={section.title}>
              <h3 className="text-sm font-semibold text-slate-900">{section.title}</h3>
              <ul className="mt-3 space-y-2">
                {section.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-sm text-slate-600 transition-colors hover:text-slate-900"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-4 border-t border-slate-200 pt-6 text-sm text-slate-500 md:flex-row md:items-center">
          <p>
            © {year} {BRAND.name} LLC. All rights reserved.
          </p>
          <p>
            Questions?{' '}
            <a href={`mailto:${BRAND.email.support}`} className="hover:text-slate-900">
              {BRAND.email.support}
            </a>
          </p>
        </div>
      </div>
    </footer>
  )
}
