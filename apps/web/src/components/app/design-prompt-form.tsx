'use client'

import { Sparkles, Wand2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import {
  DESIGN_ASPECTS,
  DESIGN_ASPECT_LABELS,
  DESIGN_STYLES,
  DESIGN_STYLE_LABELS,
  type DesignAspect,
  type DesignGenerateBody,
  type DesignStyle,
  type DesignStylePreset,
} from '@scalemyprints/contracts'

interface DesignPromptFormProps {
  onSubmit: (body: DesignGenerateBody) => void
  isLoading?: boolean
  initialPrompt?: string
  initialStyle?: DesignStyle
  initialAspect?: DesignAspect
  styles?: DesignStylePreset[]
  /** True if the user is at quota — disables the submit button. */
  quotaReached?: boolean
  submitLabel?: string
}

export function DesignPromptForm({
  onSubmit,
  isLoading = false,
  initialPrompt = '',
  initialStyle = 'minimal',
  initialAspect = 'square',
  styles,
  quotaReached = false,
  submitLabel = 'Generate design',
}: DesignPromptFormProps) {
  const [prompt, setPrompt] = useState(initialPrompt)
  const [style, setStyle] = useState<DesignStyle>(initialStyle)
  const [aspect, setAspect] = useState<DesignAspect>(initialAspect)
  const [variantCount, setVariantCount] = useState(1)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [negative, setNegative] = useState('')

  const styleOptions: DesignStylePreset[] =
    styles ??
    DESIGN_STYLES.map((id) => ({
      id,
      label: DESIGN_STYLE_LABELS[id],
      description: '',
    }))

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (prompt.trim().length < 3 || isLoading || quotaReached) return
    onSubmit({
      prompt: prompt.trim(),
      style,
      aspect,
      variant_count: variantCount,
      output_format: 'png_transparent',
      negative_prompt: negative.trim() || null,
    })
  }

  const disabled = isLoading || quotaReached || prompt.trim().length < 3

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
    >
      <div className="mb-5">
        <label
          htmlFor="design-prompt"
          className="mb-1.5 block text-sm font-medium text-slate-700"
        >
          What do you want to design?
        </label>
        <textarea
          id="design-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. a dog mom with iced coffee, hand-drawn line art, transparent background"
          required
          minLength={3}
          maxLength={600}
          rows={3}
          className="w-full resize-y rounded-lg border border-slate-300 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
        />
        <p className="mt-1 text-xs text-slate-500">
          The clearer your subject + colour palette + mood, the better the result.
        </p>
      </div>

      <div className="mb-5">
        <span className="mb-1.5 block text-sm font-medium text-slate-700">Style</span>
        <div className="flex flex-wrap gap-2">
          {styleOptions.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => setStyle(preset.id)}
              aria-pressed={style === preset.id}
              title={preset.description}
              className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                style === preset.id
                  ? 'border-primary-500 bg-primary-50 text-primary-700'
                  : 'border-slate-200 text-slate-600 hover:border-slate-300'
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-5 grid gap-4 sm:grid-cols-2">
        <div>
          <span className="mb-1.5 block text-sm font-medium text-slate-700">Aspect</span>
          <div className="flex flex-wrap gap-2">
            {DESIGN_ASPECTS.map((a) => (
              <button
                key={a}
                type="button"
                onClick={() => setAspect(a)}
                aria-pressed={aspect === a}
                className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  aspect === a
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-slate-200 text-slate-600 hover:border-slate-300'
                }`}
              >
                {DESIGN_ASPECT_LABELS[a]}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label
            htmlFor="design-variants"
            className="mb-1.5 block text-sm font-medium text-slate-700"
          >
            Variants ({variantCount})
          </label>
          <input
            id="design-variants"
            type="range"
            min={1}
            max={4}
            value={variantCount}
            onChange={(e) => setVariantCount(Number(e.target.value))}
            className="w-full"
          />
          <p className="text-xs text-slate-500">
            Each variant counts toward your monthly quota.
          </p>
        </div>
      </div>

      <details
        open={showAdvanced}
        onToggle={(e) => setShowAdvanced((e.target as HTMLDetailsElement).open)}
        className="mb-5"
      >
        <summary className="cursor-pointer text-sm font-medium text-slate-600 hover:text-slate-900">
          Advanced — negative prompt
        </summary>
        <div className="mt-3">
          <label
            htmlFor="design-negative"
            className="mb-1.5 block text-xs font-medium text-slate-600"
          >
            Avoid (e.g. &quot;text, words, blurry, gradient&quot;)
          </label>
          <input
            id="design-negative"
            type="text"
            value={negative}
            onChange={(e) => setNegative(e.target.value)}
            maxLength={400}
            placeholder="elements you don't want in the image"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 placeholder-slate-400 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
          />
        </div>
      </details>

      <button
        type="submit"
        disabled={disabled}
        className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {isLoading ? (
          <>
            <span
              className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"
              aria-hidden="true"
            />
            Generating...
          </>
        ) : (
          <>
            {quotaReached ? (
              <Sparkles className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Wand2 className="h-4 w-4" aria-hidden="true" />
            )}
            {quotaReached ? 'Quota reached — upgrade plan' : submitLabel}
          </>
        )}
      </button>
    </form>
  )
}
