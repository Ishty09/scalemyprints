/**
 * Brand identity constants.
 *
 * Single source of truth. Never hardcode brand values elsewhere.
 */

export const BRAND = {
  name: 'ScaleMyPrints',
  shortName: 'SMP',
  tagline: 'Your AI workforce for Print-on-Demand',
  description:
    'AI-powered tools that automate trend research, design generation, trademark checking, competitor tracking, and multi-platform uploading for Print-on-Demand sellers.',
  url: {
    marketing: 'https://scalemyprints.com',
    app: 'https://app.scalemyprints.com',
    api: 'https://api.scalemyprints.com',
    docs: 'https://docs.scalemyprints.com',
  },
  email: {
    support: 'support@scalemyprints.com',
    hello: 'hello@scalemyprints.com',
    security: 'security@scalemyprints.com',
    legal: 'legal@scalemyprints.com',
    dmca: 'dmca@scalemyprints.com',
  },
  social: {
    twitter: 'https://twitter.com/scalemyprints',
    instagram: 'https://instagram.com/scalemyprints',
    youtube: 'https://youtube.com/@scalemyprints',
    tiktok: 'https://tiktok.com/@scalemyprints',
    linkedin: 'https://linkedin.com/company/scalemyprints',
    discord: 'https://discord.gg/scalemyprints',
    github: 'https://github.com/scalemyprints',
  },
  colors: {
    primary: '#0D9488', // teal-600
    primaryDark: '#0F766E', // teal-700
    accent: '#F97316', // orange-500
    accentDark: '#EA580C', // orange-600
    dark: '#0F172A', // slate-900
    light: '#F8FAFC', // slate-50
  },
  fonts: {
    display: '"Cal Sans", Inter, sans-serif',
    body: 'Inter, sans-serif',
    mono: '"JetBrains Mono", monospace',
  },
} as const

export type Brand = typeof BRAND

/**
 * Tool registry.
 * All 6 tools in the ScaleMyPrints suite.
 */
export const TOOLS = {
  trademark_shield: {
    id: 'trademark_shield',
    name: 'Trademark Shield',
    slug: 'trademark',
    tagline: 'Never lose a shop to trademark strikes',
    description:
      'Multi-jurisdiction trademark risk scoring and monitoring for POD sellers. Check US, EU, UK, and Australia in seconds.',
    icon: 'Shield',
    status: 'live',
    order: 1,
  },
  niche_radar: {
    id: 'niche_radar',
    name: 'Niche Radar',
    slug: 'niche-radar',
    tagline: 'Find profitable niches before they saturate',
    description:
      'Niche Health Score across Google Trends, Etsy, and event-driven demand signals. Spot opportunities aligned with upcoming holidays.',
    icon: 'Radar',
    status: 'live',
    order: 2,
  },
  design_engine: {
    id: 'design_engine',
    name: 'Design Engine',
    slug: 'design-engine',
    tagline: 'Generate print-ready designs at scale',
    description:
      'Agentic AI design generation with multi-model orchestration, style consistency, and provenance logging.',
    icon: 'Sparkles',
    status: 'coming_soon',
    order: 3,
  },
  spy: {
    id: 'spy',
    name: 'Spy',
    slug: 'spy',
    tagline: 'Real-time competitor intelligence',
    description:
      'Track competitor shops across platforms and get velocity alerts when their listings take off.',
    icon: 'Eye',
    status: 'coming_soon',
    order: 4,
  },
  launchpad: {
    id: 'launchpad',
    name: 'Launchpad',
    slug: 'launchpad',
    tagline: 'Ship listings to 5+ platforms with one click',
    description:
      'Multi-platform listing automation with AI-optimized copy per platform. Etsy, Shopify, Printify, Amazon Merch, TikTok Shop.',
    icon: 'Rocket',
    status: 'coming_soon',
    order: 5,
  },
  pulse: {
    id: 'pulse',
    name: 'Pulse',
    slug: 'pulse',
    tagline: 'Unified POD business analytics',
    description:
      'Track revenue, profit, and performance across all platforms in one dashboard. Know which products win where.',
    icon: 'Activity',
    status: 'coming_soon',
    order: 6,
  },
} as const

export type ToolId = keyof typeof TOOLS
export type Tool = (typeof TOOLS)[ToolId]

export const TOOL_IDS: readonly ToolId[] = Object.keys(TOOLS) as ToolId[]

export const TOOLS_ORDERED: readonly Tool[] = Object.values(TOOLS).sort((a, b) => a.order - b.order)
