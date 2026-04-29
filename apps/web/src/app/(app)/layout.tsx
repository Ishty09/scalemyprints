import Link from 'next/link'
import { redirect } from 'next/navigation'
import { Activity, Eye, Radar, Rocket, Shield, Sparkles, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { BRAND, TOOLS, type ToolId } from '@scalemyprints/contracts'

import { createSupabaseServerClient } from '@/lib/supabase/server'

const SIDEBAR_ICONS: Record<ToolId, LucideIcon> = {
  trademark_shield: Shield,
  niche_radar: Radar,
  design_engine: Sparkles,
  spy: Eye,
  launchpad: Rocket,
  pulse: Activity,
}

export default async function AppLayout({ children }: { children: ReactNode }) {
  const supabase = createSupabaseServerClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login?redirect=/dashboard/trademark')
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar userEmail={user.email ?? ''} />
      <main className="flex-1">{children}</main>
    </div>
  )
}

function Sidebar({ userEmail }: { userEmail: string }) {
  return (
    <aside className="hidden w-60 flex-shrink-0 border-r border-slate-200 bg-white md:block">
      <div className="flex h-full flex-col">
        <Link href="/" className="flex items-center gap-2 border-b border-slate-200 p-4">
          <span className="rounded-md bg-gradient-to-br from-primary-600 to-accent-500 px-2 py-1 font-display text-sm font-bold text-white">
            SMP
          </span>
          <span className="font-semibold text-slate-900">{BRAND.name}</span>
        </Link>

        <nav className="flex-1 space-y-1 p-3" aria-label="Tool navigation">
          {Object.values(TOOLS).map((tool) => {
            const Icon = SIDEBAR_ICONS[tool.id]
            const isLive = tool.status === 'live'
            return (
              <Link
                key={tool.id}
                href={`/dashboard/${tool.slug}`}
                aria-disabled={!isLive}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isLive
                    ? 'text-slate-700 hover:bg-slate-100'
                    : 'cursor-not-allowed text-slate-400'
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="flex-1">{tool.name}</span>
                {!isLive && (
                  <span className="text-2xs rounded bg-slate-100 px-1.5 py-0.5 text-slate-500">
                    Soon
                  </span>
                )}
              </Link>
            )
          })}
        </nav>

        <div className="border-t border-slate-200 p-3">
          <div className="px-3 py-2 text-xs text-slate-500">
            <div className="truncate font-medium text-slate-700">{userEmail}</div>
          </div>
          <Link
            href="/dashboard/settings"
            className="block rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Settings
          </Link>
          <form action="/api/auth/logout" method="post">
            <button
              type="submit"
              className="block w-full rounded-lg px-3 py-2 text-left text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              Sign out
            </button>
          </form>
        </div>
      </div>
    </aside>
  )
}
