import Link from 'next/link'
import { Check } from 'lucide-react'

import { cn } from '@scalemyprints/utils'
import type { BundleConfig } from '@scalemyprints/contracts'

interface PricingCardProps {
  bundle: BundleConfig
}

export function PricingCard({ bundle }: PricingCardProps) {
  const highlighted = bundle.highlighted

  return (
    <div
      className={cn(
        'relative rounded-2xl border-2 p-8',
        highlighted
          ? 'border-primary-600 bg-gradient-to-br from-primary-50 to-white shadow-xl md:scale-105'
          : 'border-slate-200 bg-white',
      )}
    >
      {highlighted && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary-600 px-3 py-1 text-xs font-bold text-white">
          MOST POPULAR
        </div>
      )}

      <h3 className="font-display text-2xl font-bold text-slate-900">{bundle.name}</h3>
      <p className="mt-2 text-sm text-slate-600">{bundle.description}</p>

      <div className="mt-6">
        <div className="flex items-baseline">
          <span className="text-5xl font-bold text-slate-900">${bundle.price}</span>
          <span className="ml-1 text-slate-500">/mo</span>
        </div>
        <div className="mt-1 text-sm font-semibold text-accent-600">
          Save {bundle.savingsVsIndividual}% vs buying individually
        </div>
      </div>

      <ul className="mt-8 space-y-3">
        {bundle.features.map((feature) => (
          <li key={feature} className="flex items-start gap-2">
            <Check className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary-600" aria-hidden="true" />
            <span className="text-sm text-slate-700">{feature}</span>
          </li>
        ))}
      </ul>

      <Link
        href={`/signup?plan=${bundle.id}`}
        className={cn(
          'mt-8 block w-full rounded-lg py-3 text-center font-semibold transition-colors',
          highlighted
            ? 'bg-primary-600 text-white hover:bg-primary-700'
            : 'bg-slate-900 text-white hover:bg-slate-800',
        )}
      >
        Start {bundle.name}
      </Link>
    </div>
  )
}
