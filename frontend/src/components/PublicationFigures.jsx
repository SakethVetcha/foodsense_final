// Interactive Publication-Ready Figures and Research Export Gallery.
// Connects to /api/research/figures, /api/research/generate-figures, and /api/research/download-figure.
// Serves 300-DPI publication PNGs, scalable vector SVGs, paired CSV tables, and full zip archives.

import { useEffect, useState } from 'react'
import {
  generateResearchFigures,
  getFigureDownloadUrl,
  getResearchFigures,
} from '../api'

export default function PublicationFigures({ trace }) {
  const [figures, setFigures] = useState([])
  const [loading, setLoading] = useState(true)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState(null)
  const [selectedFig, setSelectedFig] = useState(null)

  const loadManifest = async () => {
    try {
      setLoading(true)
      const data = await getResearchFigures()
      setFigures(data)
      if (data.length > 0 && !selectedFig) {
        setSelectedFig(data[0])
      }
      setError(null)
    } catch (err) {
      setError(err.message || 'Failed to load publication figures.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadManifest()
  }, [])

  const handleRegenerate = async () => {
    try {
      setRegenerating(true)
      const updated = await generateResearchFigures(trace)
      setFigures(updated)
      if (updated.length > 0) {
        // Select matching figure or first
        const match = updated.find((f) => f.figure_id === selectedFig?.figure_id)
        setSelectedFig(match || updated[0])
      }
      setError(null)
    } catch (err) {
      setError(err.message || 'Failed to regenerate publication figures.')
    } finally {
      setRegenerating(false)
    }
  }

  // Extract filename from relative path (e.g. "results\figures\fig1.png" -> "fig1.png")
  const getBasename = (p) => {
    if (!p) return ''
    const parts = p.split(/[\\/]/)
    return parts[parts.length - 1]
  }

  return (
    <div className="bg-white border border-stone-200 rounded-xl p-5 shadow-sm space-y-6">
      {/* Header and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-stone-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-forest-700 uppercase tracking-wider bg-forest-50 px-2 py-0.5 rounded border border-forest-200">
              IEEE / Nature Style
            </span>
            <h3 className="font-bold text-forest-900 text-base">Publication-Ready Figures &amp; Data Tables</h3>
          </div>
          <p className="text-xs text-stone-500 mt-1">
            Reproducible vector SVGs, 300-DPI raster exports, paired CSV tables, and formal paper captions.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={handleRegenerate}
            disabled={regenerating}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-stone-100 hover:bg-stone-200 text-stone-700 border border-stone-300 transition flex items-center gap-1.5 disabled:opacity-50"
          >
            <span>{regenerating ? '⚡ Regenerating...' : '🔄 Re-render Figures'}</span>
          </button>

          <a
            href={getFigureDownloadUrl('foodsense_publication_figures.zip')}
            download="foodsense_publication_figures.zip"
            className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-forest-800 hover:bg-forest-900 text-white shadow-sm transition flex items-center gap-1.5"
          >
            <span>📦 Download All (.ZIP)</span>
          </a>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-xs text-stone-400">Loading figure manifest...</div>
      ) : figures.length === 0 ? (
        <div className="text-center py-8 text-xs text-stone-500">
          No figures generated yet. Click "Re-render Figures" above.
        </div>
      ) : (
        <div className="space-y-6">
          {/* Figure Selection Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-2 border-b border-stone-100">
            {figures.map((fig) => {
              const active = selectedFig?.figure_id === fig.figure_id
              return (
                <button
                  key={fig.figure_id}
                  type="button"
                  onClick={() => setSelectedFig(fig)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                    active
                      ? 'bg-forest-800 text-white shadow-sm'
                      : 'bg-stone-50 text-stone-600 hover:bg-stone-100 border border-stone-200'
                  }`}
                >
                  Fig {fig.number}: {fig.title?.split(':')[0]?.substring(0, 24)}...
                </button>
              )
            })}
          </div>

          {/* Active Figure Display */}
          {selectedFig && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Figure Preview (SVG vector format prioritized for crisp rendering) */}
              <div className="lg:col-span-8 bg-stone-50 border border-stone-200 rounded-xl p-3 flex flex-col items-center justify-center min-h-[340px]">
                <img
                  src={getFigureDownloadUrl(getBasename(selectedFig.svg_path) || getBasename(selectedFig.png_path))}
                  alt={selectedFig.title}
                  className="max-h-[380px] w-auto object-contain rounded shadow-sm bg-white p-2 border border-stone-200"
                />
                <div className="mt-3 text-[11px] text-stone-400 flex items-center gap-3">
                  <span>300 DPI Rendering</span> &middot; <span>Sans-serif Vector SVG</span> &middot;{' '}
                  <span>Targeted CMYK/RGB Color Safe</span>
                </div>
              </div>

              {/* Figure Metadata, Caption & Downloads */}
              <div className="lg:col-span-4 space-y-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-black text-forest-800 bg-forest-50 px-2 py-0.5 rounded border border-forest-200">
                      Figure {selectedFig.number}
                    </span>
                    <span className="text-[11px] text-stone-500 font-mono">
                      {selectedFig.figure_id}
                    </span>
                  </div>
                  <h4 className="font-bold text-forest-950 text-sm leading-snug">
                    {selectedFig.title}
                  </h4>
                </div>

                {/* IEEE Caption */}
                <div className="p-3 bg-stone-50 rounded-lg border border-stone-200 text-xs text-stone-700 leading-relaxed font-serif">
                  {selectedFig.caption}
                </div>

                {/* Provenance and Sample Size Badges */}
                <div className="space-y-1.5 text-xs">
                  <div className="flex items-center justify-between text-stone-600">
                    <span className="font-semibold text-stone-500">Sample Size:</span>
                    <span className="font-mono text-[11px] text-stone-800">{selectedFig.sample_size}</span>
                  </div>
                  <div className="flex items-center justify-between text-stone-600">
                    <span className="font-semibold text-stone-500">Data Grounding:</span>
                    <span className="font-mono text-[11px] text-emerald-800 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                      {selectedFig.data_source}
                    </span>
                  </div>
                </div>

                {/* Direct Download Options */}
                <div className="pt-2 border-t border-stone-200 space-y-2">
                  <div className="text-[11px] font-bold text-stone-600 uppercase tracking-wide">
                    Individual Asset Downloads
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <a
                      href={getFigureDownloadUrl(getBasename(selectedFig.png_path))}
                      download={getBasename(selectedFig.png_path)}
                      className="px-2 py-2 text-center text-xs font-bold rounded-lg bg-white hover:bg-stone-50 text-stone-800 border border-stone-300 shadow-2xs transition"
                    >
                      300-DPI PNG
                    </a>
                    <a
                      href={getFigureDownloadUrl(getBasename(selectedFig.svg_path))}
                      download={getBasename(selectedFig.svg_path)}
                      className="px-2 py-2 text-center text-xs font-bold rounded-lg bg-white hover:bg-stone-50 text-stone-800 border border-stone-300 shadow-2xs transition"
                    >
                      Vector SVG
                    </a>
                    <a
                      href={getFigureDownloadUrl(getBasename(selectedFig.csv_path))}
                      download={getBasename(selectedFig.csv_path)}
                      className="px-2 py-2 text-center text-xs font-bold rounded-lg bg-white hover:bg-stone-50 text-stone-800 border border-stone-300 shadow-2xs transition"
                    >
                      Data (CSV)
                    </a>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
