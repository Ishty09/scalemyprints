'use client'

import { ImagePlus, Loader2, X } from 'lucide-react'
import { useState } from 'react'

export function SpyReverseImageUploader({
  onSubmit,
  isLoading,
}: {
  onSubmit: (file: File) => void
  isLoading: boolean
}) {
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const f = event.target.files?.[0] ?? null
    setFile(f)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(f ? URL.createObjectURL(f) : null)
  }

  function clear() {
    setFile(null)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (file) onSubmit(file)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <label className="block text-sm font-semibold text-slate-700">
        Reverse-search a design across marketplaces
      </label>

      {!file ? (
        <label className="flex aspect-video w-full cursor-pointer items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 px-4 text-sm text-slate-500 transition hover:border-primary-400 hover:bg-primary-50/50">
          <ImagePlus className="mr-2 h-5 w-5 text-slate-400" aria-hidden />
          Drop a PNG/JPG or click to choose
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={handleChange}
            disabled={isLoading}
          />
        </label>
      ) : (
        <div className="relative overflow-hidden rounded-lg border border-slate-200">
          {previewUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={previewUrl} alt="upload preview" className="max-h-64 w-full object-contain bg-slate-50" />
          ) : null}
          <button
            type="button"
            onClick={clear}
            className="absolute right-2 top-2 rounded-full bg-slate-900/70 p-1 text-white transition hover:bg-slate-900"
            aria-label="Remove image"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          {file ? `${file.name} · ${(file.size / 1024).toFixed(0)} KB` : 'Up to 20 MB'}
        </span>
        <button
          type="submit"
          disabled={!file || isLoading}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isLoading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          {isLoading ? 'Searching…' : 'Find matches'}
        </button>
      </div>
    </form>
  )
}
