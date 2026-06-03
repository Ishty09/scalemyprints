'use client'

import { Calculator, Loader2 } from 'lucide-react'
import { useState } from 'react'

import type {
  Marketplace,
  PrinterId,
  ProductType,
  ProfitResponse,
} from '@scalemyprints/contracts'
import {
  MARKETPLACES,
  MARKETPLACE_LABELS,
  PRINTERS,
  PRINTER_LABELS,
  PRODUCT_LABELS,
} from '@scalemyprints/contracts'

import { useProfit } from '@/hooks/use-spy'

const PRODUCT_TYPES = Object.keys(PRODUCT_LABELS) as ProductType[]

export function SpyProfitCalc() {
  const profit = useProfit()
  const [marketplace, setMarketplace] = useState<Marketplace>('etsy')
  const [productType, setProductType] = useState<ProductType>('t_shirt')
  const [printer, setPrinter] = useState<PrinterId>('printify')
  const [salePrice, setSalePrice] = useState('24.99')
  const [shipping, setShipping] = useState('0')
  const [adCpc, setAdCpc] = useState('0')
  const [convRate, setConvRate] = useState('0')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    profit.mutate({
      marketplace,
      product_type: productType,
      sale_price_usd: Number(salePrice) || 0,
      printer,
      shipping_usd: Number(shipping) || 0,
      ad_cpc_usd: Number(adCpc) || 0,
      ad_conversion_rate: Number(convRate) || 0,
    })
  }

  const data: ProfitResponse | undefined = profit.data
  const negative = data && data.profit_usd < 0

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <header className="flex items-center gap-2">
        <Calculator className="h-5 w-5 text-primary-600" aria-hidden />
        <h2 className="font-display text-lg font-bold text-slate-900">Profit calculator</h2>
      </header>
      <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Marketplace">
          <select
            value={marketplace}
            onChange={(e) => setMarketplace(e.target.value as Marketplace)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          >
            {MARKETPLACES.map((m) => (
              <option key={m} value={m}>
                {MARKETPLACE_LABELS[m]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Product type">
          <select
            value={productType}
            onChange={(e) => setProductType(e.target.value as ProductType)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          >
            {PRODUCT_TYPES.map((t) => (
              <option key={t} value={t}>
                {PRODUCT_LABELS[t]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Printer">
          <select
            value={printer}
            onChange={(e) => setPrinter(e.target.value as PrinterId)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          >
            {PRINTERS.map((p) => (
              <option key={p} value={p}>
                {PRINTER_LABELS[p]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Sale price (USD)">
          <input
            type="number"
            step="0.01"
            min="0.01"
            value={salePrice}
            onChange={(e) => setSalePrice(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>

        <Field label="Shipping (USD)">
          <input
            type="number"
            step="0.01"
            min="0"
            value={shipping}
            onChange={(e) => setShipping(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>

        <Field label="Ad CPC (USD)">
          <input
            type="number"
            step="0.01"
            min="0"
            value={adCpc}
            onChange={(e) => setAdCpc(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>

        <Field label="Ad conversion rate (0-1)">
          <input
            type="number"
            step="0.001"
            min="0"
            max="1"
            value={convRate}
            onChange={(e) => setConvRate(e.target.value)}
            className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm"
          />
        </Field>

        <div className="flex items-end">
          <button
            type="submit"
            disabled={profit.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {profit.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            Calculate
          </button>
        </div>
      </form>

      {data && (
        <div
          className={`grid grid-cols-2 gap-3 rounded-lg border p-3 text-sm sm:grid-cols-3 ${
            negative
              ? 'border-rose-200 bg-rose-50'
              : 'border-emerald-200 bg-emerald-50'
          }`}
        >
          <StatRow label="Sale price" value={`$${data.sale_price_usd.toFixed(2)}`} />
          <StatRow label="Base cost" value={`$${data.base_cost_usd.toFixed(2)}`} />
          <StatRow label="Platform fee" value={`$${data.marketplace_fee_usd.toFixed(2)}`} />
          <StatRow label="Shipping" value={`$${data.shipping_usd.toFixed(2)}`} />
          <StatRow label="Ad cost" value={`$${data.ad_cost_usd.toFixed(2)}`} />
          <StatRow
            label="Profit / margin"
            value={`$${data.profit_usd.toFixed(2)} · ${data.margin_pct.toFixed(1)}%`}
            emphasis
            negative={negative}
          />
          {data.note && (
            <p className="col-span-full text-xs text-slate-600">{data.note}</p>
          )}
        </div>
      )}
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
    </label>
  )
}

function StatRow({
  label,
  value,
  emphasis,
  negative,
}: {
  label: string
  value: string
  emphasis?: boolean
  negative?: boolean | undefined
}) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div
        className={`font-semibold ${
          emphasis
            ? negative
              ? 'text-rose-700'
              : 'text-emerald-700'
            : 'text-slate-900'
        }`}
      >
        {value}
      </div>
    </div>
  )
}
