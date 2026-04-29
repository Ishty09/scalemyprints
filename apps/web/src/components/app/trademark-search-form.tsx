'use client'

import { Search } from 'lucide-react'
import { useState } from 'react'

import {
  JURISDICTION_NAMES,
  POD_RELEVANT_NICE_CLASSES,
  TRADEMARK_SEARCH_REQUEST_SCHEMA,
  type JurisdictionCode,
  type NiceClass,
  type TrademarkSearchRequest,
} from '@scalemyprints/contracts'
import { cn } from '@scalemyprints/utils'

import { Button } from '@/components/ui'

const JURISDICTION_OPTIONS: JurisdictionCode[] = ['US', 'EU', 'UK', 'AU']
const COMMON_NICE_CLASSES: NiceClass[] = [25, 21, 16, 28]

interface TrademarkSearchFormProps {
  onSearch: (request: TrademarkSearchRequest) => void
  isLoading: boolean
}

export function TrademarkSearchForm({ onSearch, isLoading }: TrademarkSearchFormProps) {
  const [phrase, setPhrase] = useState('')
  const [jurisdictions, setJurisdictions] = useState<JurisdictionCode[]>(['US', 'EU', 'AU'])
  const [niceClasses, setNiceClasses] = useState<NiceClass[]>([25])
  const [validationError, setValidationError] = useState<string | null>(null)

  function toggleJurisdiction(code: JurisdictionCode) {
    setJurisdictions((current) =>
      current.includes(code) ? current.filter((j) => j !== code) : [...current, code],
    )
  }

  function toggleNiceClass(cls: NiceClass) {
    setNiceClasses((current) =>
      current.includes(cls) ? current.filter((c) => c !== cls) : [...current, cls],
    )
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setValidationError(null)

    const candidate: TrademarkSearchRequest = {
      phrase: phrase.trim(),
      jurisdictions,
      nice_classes: niceClasses,
      check_common_law: false,
    }
    const result = TRADEMARK_SEARCH_REQUEST_SCHEMA.safeParse(candidate)
    if (!result.success) {
      const first = result.error.errors[0]
      setValidationError(first?.message ?? 'Invalid input')
      return
    }
    onSearch(result.data)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border border-slate-200 bg-white p-6"
      noValidate
    >
      <div className="mb-4">
        <label
          htmlFor="trademark-phrase"
          className="mb-2 block text-sm font-medium text-slate-700"
        >
          Phrase to check
        </label>
        <input
          id="trademark-phrase"
          type="text"
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          placeholder="e.g., Lucky Mama Teacher Life"
          maxLength={200}
          className={cn(
            'h-12 w-full rounded-lg border bg-white px-4 text-base text-slate-900',
            'placeholder:text-slate-400 transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-offset-1',
            validationError
              ? 'border-danger-500 focus:border-danger-500 focus:ring-danger-500'
              : 'border-slate-300 focus:border-primary-600 focus:ring-primary-600',
          )}
          aria-invalid={validationError ? 'true' : undefined}
          aria-describedby={validationError ? 'phrase-error' : undefined}
          required
        />
        {validationError && (
          <p id="phrase-error" className="mt-2 text-sm text-danger-600">
            {validationError}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <fieldset>
            <legend className="mb-2 block text-sm font-medium text-slate-700">
              Jurisdictions
            </legend>
            <div className="flex flex-wrap gap-2">
              {JURISDICTION_OPTIONS.map((code) => (
                <ToggleChip
                  key={code}
                  label={code}
                  ariaLabel={JURISDICTION_NAMES[code]}
                  active={jurisdictions.includes(code)}
                  onClick={() => toggleJurisdiction(code)}
                />
              ))}
            </div>
          </fieldset>
        </div>

        <div>
          <fieldset>
            <legend className="mb-2 block text-sm font-medium text-slate-700">
              Nice classes
            </legend>
            <div className="flex flex-wrap gap-2">
              {COMMON_NICE_CLASSES.map((cls) => (
                <ToggleChip
                  key={cls}
                  label={`Class ${cls}`}
                  ariaLabel={POD_RELEVANT_NICE_CLASSES[cls] ?? `Class ${cls}`}
                  active={niceClasses.includes(cls)}
                  onClick={() => toggleNiceClass(cls)}
                />
              ))}
            </div>
          </fieldset>
        </div>
      </div>

      <Button
        type="submit"
        size="lg"
        isLoading={isLoading}
        disabled={!phrase.trim()}
        leftIcon={!isLoading ? <Search className="h-4 w-4" /> : undefined}
        className="mt-6 w-full"
      >
        {isLoading ? 'Analyzing...' : 'Check trademark risk'}
      </Button>
    </form>
  )
}

interface ToggleChipProps {
  label: string
  ariaLabel: string
  active: boolean
  onClick: () => void
}

function ToggleChip({ label, ariaLabel, active, onClick }: ToggleChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={ariaLabel}
      className={cn(
        'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-primary-600 text-white'
          : 'bg-slate-100 text-slate-700 hover:bg-slate-200',
      )}
    >
      {label}
    </button>
  )
}
