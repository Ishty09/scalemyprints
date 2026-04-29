import Link from 'next/link'
import { ArrowRight, CheckCircle, Shield } from 'lucide-react'

import { TOOLS, TRADEMARK_SHIELD_PLANS } from '@scalemyprints/contracts'

import { MarketingFooter } from '@/components/marketing/marketing-footer'
import { MarketingNav } from '@/components/marketing/marketing-nav'

export default function TrademarkShieldPage() {
  const tool = TOOLS.trademark_shield

  const features = [
    {
      title: 'Multi-jurisdiction in one search',
      body: 'Hit USPTO, EUIPO, IP Australia, and the UK office in parallel. Results in seconds.',
    },
    {
      title: 'Smart risk scoring',
      body: 'Our weighted algorithm considers active registrations, pending applications, related Nice classes, common-law density, and phrase distinctiveness.',
    },
    {
      title: 'Arbitrage opportunities',
      body: 'When a phrase is risky in one country but safe elsewhere, we tell you exactly where to sell.',
    },
    {
      title: 'Continuous monitoring',
      body: 'Set up watches and get alerts the moment a new filing in your space appears.',
    },
    {
      title: 'Free Chrome extension',
      body: 'Check trademark risk on any Etsy or Amazon listing with one click. No login needed for the first 5 searches a day.',
    },
  ]

  return (
    <>
      <MarketingNav />
      <main className="px-6">
        <section className="mx-auto max-w-4xl pt-16 pb-12 text-center">
          <div className="mx-auto inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-100 text-primary-600">
            <Shield className="h-7 w-7" aria-hidden="true" />
          </div>
          <h1 className="mt-6 font-display text-5xl font-bold tracking-tight text-slate-900 md:text-6xl">
            {tool.tagline}
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
            {tool.description} Catch infringement risks <em>before</em> you list — not after a
            takedown notice.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-600 px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-primary-700"
            >
              Try free — 5 searches/mo
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <a
              href="#pricing"
              className="text-sm font-medium text-slate-700 hover:text-slate-900"
            >
              See plans →
            </a>
          </div>
        </section>

        <section className="mx-auto max-w-5xl py-16">
          <h2 className="mb-12 text-center font-display text-3xl font-bold text-slate-900">
            What you get
          </h2>
          <div className="grid gap-6 md:grid-cols-2">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="rounded-2xl border border-slate-200 bg-white p-6"
              >
                <div className="mb-3 flex items-center gap-2">
                  <CheckCircle className="h-5 w-5 text-primary-600" aria-hidden="true" />
                  <h3 className="font-semibold text-slate-900">{feature.title}</h3>
                </div>
                <p className="text-sm text-slate-600">{feature.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-5xl py-16" id="pricing">
          <h2 className="mb-12 text-center font-display text-3xl font-bold text-slate-900">
            Trademark Shield plans
          </h2>
          <div className="grid gap-6 md:grid-cols-4">
            {Object.entries(TRADEMARK_SHIELD_PLANS).map(([tier, plan]) => (
              <div
                key={tier}
                className="rounded-2xl border border-slate-200 bg-white p-6"
              >
                <h3 className="font-display text-xl font-bold capitalize text-slate-900">{tier}</h3>
                <div className="mt-3">
                  <span className="text-3xl font-bold">${plan.price}</span>
                  <span className="text-slate-500">/mo</span>
                </div>
                <ul className="mt-4 space-y-1.5 text-sm text-slate-600">
                  {Object.entries(plan.limits).map(([key, value]) => (
                    <li key={key} className="flex items-start gap-1.5">
                      <CheckCircle
                        className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-primary-600"
                        aria-hidden="true"
                      />
                      <span>
                        {formatLimitKey(key)}:{' '}
                        <strong>{formatLimitValue(value)}</strong>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-8 text-center text-sm text-slate-500">
            Need multiple tools? Save 40%+ with a{' '}
            <Link href="/pricing" className="font-medium text-primary-600 hover:underline">
              bundle plan
            </Link>
            .
          </p>
        </section>
      </main>
      <MarketingFooter />
    </>
  )
}

function formatLimitKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatLimitValue(value: number | boolean): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (value === -1) return 'Unlimited'
  return value.toLocaleString()
}
