// Lab findings, shown only when a lab report was supplied.
//
// Kept visually distinct from the meal plan because it is a different kind of
// statement: the meal plan is computed from IFCT, the lab findings are advisory
// interpretations of the user's own numbers.

const STATUS_TONE = {
  low: 'bg-amber-100 text-amber-800 border-amber-300',
  high: 'bg-rose-100 text-rose-800 border-rose-300',
  normal: 'bg-emerald-100 text-emerald-800 border-emerald-300',
}

export default function LabFindings({ report }) {
  if (!report) return null
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <h3 className="font-semibold text-slate-800 text-sm mb-2">Laboratory markers</h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-3">
        {report.markers.map((m) => (
          <div key={m.key} className="border border-slate-200 rounded-lg px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-700">{m.label}</span>
              <span
                className={`text-[10px] uppercase border rounded-full px-2 py-0.5 font-semibold ${STATUS_TONE[m.status] || ''}`}
              >
                {m.status}
              </span>
            </div>
            <div className="text-xs text-slate-500 font-mono mt-1">
              {m.value} {m.unit}
              {m.reference_low != null && m.reference_high != null && (
                <span className="text-slate-400"> · ref {m.reference_low}–{m.reference_high}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {report.findings.length > 0 && (
        <div className="space-y-1.5">
          {report.findings.map((f, i) => (
            <div key={i} className="text-sm bg-slate-50 border border-slate-200 rounded p-2">
              <span className="font-medium text-slate-800">{f.label}</span>{' '}
              <span className="text-slate-500">({f.status})</span>
              <p className="text-slate-600 mt-0.5">{f.message}</p>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-slate-500 mt-3 italic">{report.disclaimer}</p>
    </div>
  )
}
