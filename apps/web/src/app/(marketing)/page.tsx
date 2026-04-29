import Link from 'next/link'
import {
  Activity,
  ArrowRight,
  Eye,
  Radar,
  Rocket,
  Shield,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'

import {
  BUNDLES,
  FOUNDING_MEMBER,
  TOOLS,
  TOOLS_ORDERED,
  type ToolId,
} from '@scalemyprints/contracts'

import { MarketingFooter } from '@/components/marketing/marketing-footer'
import { MarketingNav } from '@/components/marketing/marketing-nav'
import { PricingCard } from '@/components/marketing/pricing-card'
import { ToolCard } from '@/components/marketing/tool-card'

const TOOL_ICONS: Record<ToolId, LucideIcon> = {
  trademark_shield: Shield,
  niche_radar: Radar,
  design_engine: Sparkles,
  spy: Eye,
  launchpad: Rocket,
  pulse: Activity,
}

export default function HomePage() {
  return (
    <>
      <MarketingNav />
      <main>
        <Hero />
        <ToolsGrid />
        <Pricing />
      </main>
      <MarketingFooter />
    </>
  )
}

function Hero() {
  return (
    <section className="px-6 pb-20 pt-16 md:pt-24">
      <div className="mx-auto max-w-5xl text-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-primary-50 px-4 py-2 text-sm font-medium text-primary-700">
          <span className="h-2 w-2 animate-pulse rounded-full bg-primary-500" aria-hidden="true" />
          Now in private beta · Founding members get {FOUNDING_MEMBER.discountPercent}% off for life
        </div>

        <h1 className="mt-8 font-display text-5xl font-bold tracking-tight text-slate-900 md:text-7xl">
          Your AI workforce for
          <br />
          <span className="text-gradient-brand">Print-on-Demand</span>
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600 md:text-xl">
          6 AI-powered tools that automate trend research, design generation, trademark checking,
          competitor tracking, and multi-platform uploading. Stop grinding. Start shipping.
        </p>

        <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
          <Link
            href="/signup"
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-600 px-8 py-4 text-base font-semibold text-white transition-colors hover:bg-primary-700"
          >
            Start free — no credit card
            <ArrowRight className="h-5 w-5" aria-hidden="true" />
          </Link>
          <Link
            href="/trademark-shield"
            className="inline-flex items-center gap-1 text-sm font-medium text-slate-700 hover:text-slate-900"
          >
            Try Trademark Shield free
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>

        <p className="mt-6 text-sm text-slate-500">
          ⚡ 5 free trademark searches per month forever
        </p>
      </div>
    </section>
  )
}

function ToolsGrid() {
  return (
    <section className="bg-slate-50 px-6 py-20">
      <div className="mx-auto max-w-7xl">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-display text-4xl font-bold text-slate-900">
            6 tools. One platform. Zero grinding.
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            Each tool handles a different part of your POD business, powered by agentic AI that
            actually does the work.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {TOOLS_ORDERED.map((tool) => (
            <ToolCard key={tool.id} tool={tool} Icon={TOOL_ICONS[tool.id]} />
          ))}
        </div>
      </div>
    </section>
  )
}

function Pricing() {
  const bundles = [BUNDLES.core, BUNDLES.pro, BUNDLES.empire]

  return (
    <section className="px-6 py-20" id="pricing">
      <div className="mx-auto max-w-5xl">
        <div className="mb-12 text-center">
          <h2 className="font-display text-4xl font-bold text-slate-900">Save more with bundles</h2>
          <p className="mt-4 text-lg text-slate-600">
            Bundles include multiple tools at up to 42% savings vs buying individually.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {bundles.map((bundle) => (
            <PricingCard key={bundle.id} bundle={bundle} />
          ))}
        </div>

        <p className="mt-8 text-center text-sm text-slate-500">
          💎 Founding members: First {FOUNDING_MEMBER.limit} users get{' '}
          {FOUNDING_MEMBER.discountPercent}% off for life. Limited spots available.
        </p>
      </div>
    </section>
  )
}
