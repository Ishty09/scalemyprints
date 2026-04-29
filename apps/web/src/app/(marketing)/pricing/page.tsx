import { BUNDLES, FOUNDING_MEMBER } from '@scalemyprints/contracts'

import { MarketingFooter } from '@/components/marketing/marketing-footer'
import { MarketingNav } from '@/components/marketing/marketing-nav'
import { PricingCard } from '@/components/marketing/pricing-card'

export const metadata = {
  title: 'Pricing — Bundles save up to 42%',
  description:
    'Three bundle tiers for solo sellers, pros, and agencies. Founding members get 40% off for life.',
}

export default function PricingPage() {
  const bundles = [BUNDLES.core, BUNDLES.pro, BUNDLES.empire]

  return (
    <>
      <MarketingNav />
      <main>
        <section className="px-6 pt-16 pb-12 text-center">
          <h1 className="font-display text-5xl font-bold tracking-tight text-slate-900 md:text-6xl">
            Simple bundle pricing
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600">
            Three tiers for solo sellers, pros, and agencies. Save up to 42% vs buying tools
            individually. Cancel anytime.
          </p>
        </section>

        <section className="px-6 pb-16">
          <div className="mx-auto max-w-5xl">
            <div className="grid gap-6 md:grid-cols-3">
              {bundles.map((bundle) => (
                <PricingCard key={bundle.id} bundle={bundle} />
              ))}
            </div>
            <p className="mt-8 text-center text-sm text-slate-500">
              💎 First {FOUNDING_MEMBER.limit} users get {FOUNDING_MEMBER.discountPercent}% off for
              life. Available at signup.
            </p>
          </div>
        </section>

        <section className="bg-slate-50 px-6 py-16">
          <div className="mx-auto max-w-3xl">
            <h2 className="mb-8 text-center font-display text-3xl font-bold text-slate-900">
              FAQ
            </h2>
            <div className="space-y-6">
              <FAQ
                question="Can I cancel anytime?"
                answer="Yes — no contracts, no cancellation fees. Cancel from your settings page and you'll keep access until the end of your billing period."
              />
              <FAQ
                question="Do annual plans get a discount?"
                answer="Yes — pay annually and get 25% off. The annual price shown saves you 3 months compared to monthly billing."
              />
              <FAQ
                question="What does Founding Member status mean?"
                answer={`The first ${FOUNDING_MEMBER.limit} paid users get ${FOUNDING_MEMBER.discountPercent}% off for life on any plan. The discount never expires, even if you upgrade or downgrade.`}
              />
              <FAQ
                question="Can I buy individual tools without a bundle?"
                answer="Yes — every tool has its own pricing tiers. Visit the tool's product page to see options. Bundles save 37–42% if you need multiple tools."
              />
              <FAQ
                question="Is there a free tier?"
                answer="Yes — Trademark Shield includes 5 free searches per month forever. No credit card required."
              />
            </div>
          </div>
        </section>
      </main>
      <MarketingFooter />
    </>
  )
}

function FAQ({ question, answer }: { question: string; answer: string }) {
  return (
    <details className="group rounded-lg border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer text-sm font-semibold text-slate-900 group-open:mb-2">
        {question}
      </summary>
      <p className="text-sm text-slate-600">{answer}</p>
    </details>
  )
}
