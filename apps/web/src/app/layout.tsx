import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { Toaster } from 'sonner'
import type { ReactNode } from 'react'

import { BRAND } from '@scalemyprints/contracts'

import { QueryProvider } from '@/components/providers/query-provider'
import '@/styles/globals.css'

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: {
    default: `${BRAND.name} — ${BRAND.tagline}`,
    template: `%s | ${BRAND.name}`,
  },
  description: BRAND.description,
  metadataBase: new URL(BRAND.url.marketing),
  openGraph: {
    type: 'website',
    siteName: BRAND.name,
    title: `${BRAND.name} — ${BRAND.tagline}`,
    description: BRAND.description,
  },
  twitter: {
    card: 'summary_large_image',
    site: '@scalemyprints',
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <QueryProvider>
          {children}
          <Toaster position="top-right" richColors closeButton />
        </QueryProvider>
      </body>
    </html>
  )
}
