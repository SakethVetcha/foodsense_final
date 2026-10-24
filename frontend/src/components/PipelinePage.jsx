import { useEffect, useState } from 'react'
import {
  exportTrace,
  getHealth,
  getIndianScenarios,
  getProviders,
  getResearchEvalData,
  getScenarios,
  recommend,
} from '../api'
import CustomBuilder from './CustomBuilder'
import MealDiff from './MealDiff'
import Metrics from './Metrics'
import PublicationFigures from './PublicationFigures'
import {
  AcademicBenchmarkCharts,
  ConvergenceTrajectoryChart,
  CounterfactualEditsChart,
  FoodSourceCompositionChart,
  NutrientChangeChart,
  NutrientComparisonChart,
  TargetVsAchievedChart,
  VerificationDiscrepancyChart,
} from './ResearchCharts'
import Stepper from './Stepper'
import Verification, { Badge } from './Verification'

// The four-stage counterfactual research pipeline: primary integrated research experience.
// Incorporates unified USDA and IFCT 2017 food composition databases, availability-aware
// differential evolution, ICMR-NIN single-meal RDA compliance, and multi-source verification.

function MealSummarySideBySide({ plannedMeal, counterfactualMeal }) {
  if (!plannedMeal || !counterfactualMeal) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Planned Meal Card */}
      <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm space-y-3">
        <div className="flex items-center justify-between border-b border-stone-100 pb-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
            <h4 className="font-bold text-stone-800 text-sm">Initial Planned Meal (Stage 1)</h4>
          </div>
          <span className="text-xs font-mono text-stone-500">
            {plannedMeal.items?.length || 0} items
          </span>
        </div>
        <ul className="divide-y divide-stone-100 text-xs">
          {plannedMeal.items?.map((it, i) => (
            <li key={i} className="py-2 flex items-center justify-between">
              <div>
                <span className="font-medium text-stone-800">{it.name}</span>
                <span className="block text-[11px] text-stone-400">
                  Form: {it.form || 'whole'} &middot; Source:{' '}
                  {it.source || (it.food_id?.startsWith('IF') ? 'IFCT_2017' : 'USDA')}
                </span>
              </div>
              <span className="font-mono font-bold text-stone-700">{it.quantity_g?.toFixed(0)}g</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Counterfactual Meal Card */}
      <div className="bg-white border border-emerald-200 rounded-xl p-4 shadow-sm space-y-3">
        <div className="flex items-center justify-between border-b border-emerald-100 pb-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-600" />
            <h4 className="font-bold text-forest-900 text-sm">Optimized Counterfactual Meal (Stage 4)</h4>
          </div>
          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
            Verified Safe &amp; Available
          </span>
        </div>
        <ul className="divide-y divide-stone-100 text-xs">
          {counterfactualMeal.items?.map((it, i) => (
            <li key={i} className="py-2 flex items-center justify-between">
              <div>
                <span className="font-semibold text-stone-900">{it.name}</span>
                <span className="block text-[11px] text-emerald-700">
                  Form: <strong className="font-bold">{it.form || 'whole'}</strong> &middot;{' '}
                  <span className="text-stone-500">
                    {it.source || (it.food_id?.startsWith('IF') ? 'IFCT_2017' : 'USDA')}
                  </span>
                </span>
              </div>
              <span className="font-mono font-bold text-emerald-900">{it.quantity_g?.toFixed(0)}g</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function IngredientChangeTable({ diff }) {
  if (!diff) return null
  const changes = diff.changes || []
  const edits = changes.filter((c) => c.change_type !== 'unchanged')
  const kept = changes.filter((c) => c.change_type === 'unchanged')

  return (
    <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 border-b border-stone-100 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h4 className="font-bold text-forest-900 text-sm">Detailed Ingredient Counterfactual Audit</h4>
          <p className="text-xs text-stone-500">
            Ingredient substitutions, additions, removals, portion scaling, and preparation-form transitions.
          </p>
        </div>
        <span className="text-xs font-semibold px-2.5 py-0.5 rounded bg-stone-100 text-stone-700 border border-stone-200">
          {edits.length} edits &middot; {kept.length} kept unchanged &middot; {Math.round(diff.l1_distance_g)}g moved
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left">
          <thead className="bg-stone-50 text-stone-600 font-semibold border-b border-stone-200">
            <tr>
              <th className="py-2.5 px-3">Operation</th>
              <th className="py-2.5 px-3">Food Item</th>
              <th className="py-2.5 px-3">Catalog Source</th>
              <th className="py-2.5 px-3 text-right">Planned (g)</th>
              <th className="py-2.5 px-3 text-right">Counterfactual (g)</th>
              <th className="py-2.5 px-3">Form Transition</th>
              <th className="py-2.5 px-3">Optimization Rationale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {changes.map((c, i) => {
              const isEdit = c.change_type !== 'unchanged'
              const opTone =
                c.change_type === 'added'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : c.change_type === 'removed'
                  ? 'bg-rose-50 text-rose-800 border-rose-200'
                  : c.change_type === 'modified'
                  ? 'bg-amber-50 text-amber-800 border-amber-200'
                  : 'bg-stone-50 text-stone-500 border-stone-200'

              const srcTone =
                c.source === 'IFCT_2017'
                  ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                  : c.source === 'COMPOSITE'
                  ? 'text-amber-700 bg-amber-50 border-amber-200'
                  : 'text-sky-700 bg-sky-50 border-sky-200'

              return (
                <tr
                  key={i}
                  className={isEdit ? 'bg-white hover:bg-stone-50/70' : 'bg-stone-50/40 opacity-75'}
                >
                  <td className="py-2 px-3">
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase border ${opTone}`}>
                      {c.change_type}
                    </span>
                  </td>
                  <td className="py-2 px-3 font-medium text-stone-800">
                    {c.name}
                    <span className="block font-mono text-[10px] text-stone-400">{c.food_id}</span>
                  </td>
                  <td className="py-2 px-3">
                    <span className={`px-1.5 py-0.5 text-[10px] font-semibold rounded border ${srcTone}`}>
                      {c.source || (c.food_id?.startsWith('IF') ? 'IFCT_2017' : 'USDA')}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-stone-600">
                    {c.old_quantity_g != null ? `${c.old_quantity_g.toFixed(0)}g` : '—'}
                  </td>
                  <td className="py-2 px-3 text-right font-mono font-bold text-forest-900">
                    {c.new_quantity_g != null ? `${c.new_quantity_g.toFixed(0)}g` : '—'}
                  </td>
                  <td className="py-2 px-3">
                    {c.old_form && c.new_form && c.old_form !== c.new_form ? (
                      <span className="font-semibold text-amber-800 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                        {c.old_form} &rarr; {c.new_form}
                      </span>
                    ) : (
                      <span className="text-stone-400">{c.new_form || c.old_form || 'standard'}</span>
                    )}
                  </td>
                  <td className="py-2 px-3 text-stone-600 text-[11px] leading-snug">
                    {c.reason || 'Optimal nutritional trade-off satisfying macro and availability constraints'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FourStageDiagnosticsCards({ trace }) {
  if (!trace) return null
  const s1 = trace.stage1
  const s2 = trace.stage2
  const s3 = trace.stage3
  const s4 = trace.stage4

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Stage 1 Card */}
      <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm space-y-2.5">
        <div className="flex items-center justify-between border-b border-stone-100 pb-2">
          <span className="text-[11px] font-bold text-forest-700 uppercase tracking-wide">Stage 1</span>
          <span className="text-[10px] font-mono text-stone-400">{s1.model_name}</span>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-stone-500">Predicted Suitability</div>
          <div className="text-xl font-black text-forest-950">{s1.suitability.toFixed(3)}</div>
          <div className="text-[11px] text-stone-600">
            Rule engine soft score: <strong>{s1.rule_evaluation?.score.toFixed(3)}</strong>
          </div>
        </div>
        <div className="pt-2 border-t border-stone-100 text-[11px] text-stone-500 space-y-1">
          <div>
            Status:{' '}
            {s1.is_ood ? (
              <span className="font-semibold text-amber-700">Out-of-Distribution (Indian Data)</span>
            ) : (
              <span className="font-semibold text-emerald-700">In-Distribution</span>
            )}
          </div>
          <div>Adapter: <code className="text-[10px] font-mono text-stone-700">{s1.prediction_source}</code></div>
          {s1.is_ood && (
            <p className="text-[10px] text-amber-800 bg-amber-50 p-1.5 rounded border border-amber-200">
              Evaluated with source-aware nutrient adapter and deterministic rule grounding.
            </p>
          )}
        </div>
      </div>

      {/* Stage 2 Card */}
      <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm space-y-2.5">
        <div className="flex items-center justify-between border-b border-stone-100 pb-2">
          <span className="text-[11px] font-bold text-forest-700 uppercase tracking-wide">Stage 2</span>
          <span className="text-[10px] font-mono text-stone-400">{s2.method}</span>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-stone-500">Optimization Objective</div>
          <div className="text-xl font-black text-forest-950">{s2.objective_value.toFixed(4)}</div>
          <div className="text-[11px] text-stone-600">
            L1 Edit Distance: <strong>{Math.round(s2.diff?.l1_distance_g || 0)}g</strong> ({s2.diff?.n_items_changed || 0} edits)
          </div>
        </div>
        <div className="pt-2 border-t border-stone-100 text-[11px] text-stone-500 space-y-1">
          <div>Convergence: <span className="font-semibold text-emerald-700">Target Reached ({s2.n_generations} gen)</span></div>
          <div>Search space: <span className="font-mono">{s2.search_space_size} available foods</span></div>
          <div>Evaluations: <span className="font-mono">{s2.n_evaluations?.toLocaleString()} runs</span></div>
        </div>
      </div>

      {/* Stage 3 Card */}
      <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm space-y-2.5">
        <div className="flex items-center justify-between border-b border-stone-100 pb-2">
          <span className="text-[11px] font-bold text-forest-700 uppercase tracking-wide">Stage 3</span>
          <span className="text-[10px] font-mono text-stone-400">provider: {s3.provider}</span>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-stone-500">Recommendation Grounding</div>
          <div className="text-sm font-bold text-stone-800 line-clamp-2">
            {s3.fallback_used ? 'Offline Deterministic Template' : 'Grounded LLM Rationale'}
          </div>
          {s3.fallback_used && (
            <span className="inline-block text-[10px] font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
              Offline First · No Key Required
            </span>
          )}
        </div>
        <div className="pt-2 border-t border-stone-100 text-[11px] text-stone-500 space-y-1">
          <div>Rationale points: <strong className="text-stone-800">{s3.rationale?.length || 0} items</strong></div>
          <div>Runtime: <span className="font-mono">{(s3.runtime_s * 1000).toFixed(0)} ms</span></div>
        </div>
      </div>

      {/* Stage 4 Card */}
      <div className="bg-white border border-stone-200 rounded-xl p-4 shadow-sm space-y-2.5">
        <div className="flex items-center justify-between border-b border-stone-100 pb-2">
          <span className="text-[11px] font-bold text-forest-700 uppercase tracking-wide">Stage 4</span>
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
            s4.final_pass ? 'bg-emerald-50 text-emerald-800 border-emerald-300' : 'bg-rose-50 text-rose-800 border-rose-300'
          }`}>
            {s4.final_pass ? 'PASS' : 'ISSUES DETECTED'}
          </span>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-stone-500">Independent Verification</div>
          <div className="text-xl font-black text-forest-950">
            {s4.matched} / {s4.checked} <span className="text-xs font-normal text-stone-500">items checked</span>
          </div>
          <div className="text-[11px] text-stone-600">
            Corrections: <strong>{s4.n_corrections || 0}</strong> &middot; Safety fixes: <strong>{s4.safety_fixes?.length || 0}</strong>
          </div>
        </div>
        <div className="pt-2 border-t border-stone-100 text-[11px] text-stone-500 space-y-1">
          <div className="flex items-center gap-1 flex-wrap">
            <span>Sources:</span>
            {Object.entries(s4.source_breakdown || {}).map(([src, count]) => (
              <span key={src} className="font-mono text-[10px] font-bold text-stone-700 bg-stone-100 px-1 py-0.5 rounded">
                {src}: {count}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function StagePanel({ stage, trace }) {
  if (!trace) return null

  if (stage === 'stage1') {
    const s = trace.stage1
    const ev = s.rule_evaluation
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-slate-800">Stage 1 &mdash; the planned meal, scored</h3>
          <div className="flex items-center gap-1.5">
            {s.is_ood ? (
              <Badge tone="warn">OOD &middot; Indian Nutrition</Badge>
            ) : (
              <Badge tone="pass">In-Distribution (Food.com)</Badge>
            )}
            <span className="text-xs font-mono text-slate-500">adapter: {s.prediction_source}</span>
          </div>
        </div>

        {s.is_ood && (
          <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 text-amber-900 text-xs">
            <div className="font-bold flex items-center gap-1.5 mb-1 text-amber-950">
              <span>⚠️</span> Out-of-Distribution (OOD) Machine Learning Notice
            </div>
            <p>
              {s.confidence_note ||
                'This meal contains Indian foods (IFCT 2017 / composite dishes) not represented in the Food.com surrogate training set. Evaluated using transparent unit conversion and source-aware rule engine verification.'}
            </p>
          </div>
        )}

        <p className="text-sm text-slate-600">
          Suitability <strong>{s.suitability.toFixed(3)}</strong> from{' '}
          <span className="font-mono text-xs">{s.model_name}</span>; the rule engine scores it{' '}
          <strong>{ev.score.toFixed(3)}</strong>.
        </p>
        {ev.violations?.length > 0 ? (
          <ul className="space-y-1">
            {ev.violations.map((v, i) => (
              <li
                key={i}
                className={`text-sm border rounded p-2 ${
                  v.severity === 'hard'
                    ? 'bg-rose-50 border-rose-200'
                    : 'bg-amber-50 border-amber-200'
                }`}
              >
                <div className="flex items-center gap-2">
                  <Badge tone={v.severity === 'hard' ? 'fail' : 'warn'}>{v.severity}</Badge>
                  <span className="font-mono text-xs text-slate-600">{v.rule_id}</span>
                </div>
                <div className="text-slate-800 mt-1">{v.message}</div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500 italic">This meal breaks no rule.</p>
        )}
      </div>
    )
  }

  if (stage === 'stage2') {
    const s = trace.stage2
    if (!s) return <p className="text-sm text-slate-500">Stage 2 did not run.</p>
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-slate-800">Stage 2 &mdash; the counterfactual</h3>
          {s.valid ? (
            <Badge tone="pass">reached the target</Badge>
          ) : (
            <Badge tone="warn">best safe edit found</Badge>
          )}
        </div>
        <p className="text-sm text-slate-600">
          {s.n_generations} generations, {s.n_evaluations.toLocaleString()} evaluations over a
          search space of {s.search_space_size} foods &mdash; every one of them strictly from the planned
          meal or the user&rsquo;s pantry.
        </p>
        <MealDiff diff={s.diff} />
      </div>
    )
  }

  if (stage === 'stage3') {
    const s = trace.stage3
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-slate-800">Stage 3 &mdash; the explanation</h3>
          <Badge tone="quiet">{s.provider}</Badge>
          {s.fallback_used && <Badge tone="warn">fell back to template</Badge>}
        </div>
        {s.fallback_used && s.fallback_reason && (
          <p className="text-sm bg-amber-50 border border-amber-200 rounded p-2 text-amber-900">
            {s.fallback_reason}
          </p>
        )}
        <p className="text-slate-800 whitespace-pre-wrap">{s.text}</p>
        {s.rationale?.length > 0 && (
          <ul className="text-sm text-slate-700 list-disc list-inside space-y-0.5">
            {s.rationale.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  return <Verification report={trace.stage4} />
}

const CUSTOM_KEY = '__custom__'

const toMealItem = (item) => ({
  food_id: item.food_id,
  name: item.name,
  quantity_g: Number(item.quantity_g),
  form: item.form,
  source: item.source,
})

export default function PipelinePage() {
  const [scenarios, setScenarios] = useState([])
  const [indianScenarios, setIndianScenarios] = useState([])
  const [providers, setProviders] = useState([])
  const [health, setHealth] = useState(null)
  const [scenario, setScenario] = useState('toddler_choking')
  const [provider, setProvider] = useState('template')
  const [seed, setSeed] = useState(42)
  const [trace, setTrace] = useState(null)
  const [ranWith, setRanWith] = useState(null)
  const [evalData, setEvalData] = useState(null)
  const [custom, setCustom] = useState({
    profile: {
      age_group: 'toddler',
      age_months: 18,
      weight_kg: 11,
      goal: 'balanced_nutrition',
      health_flags: [],
      life_stage: null,
      sex: null,
      diet: null,
    },
    planned: [],
    pantry: [],
  })
  const [stage, setStage] = useState('stage2')
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState(null)
  const [showJson, setShowJson] = useState(false)
  const [activeVizTab, setActiveVizTab] = useState('nutrients') // 'nutrients' | 'trajectory' | 'verification' | 'benchmarks' | 'figures'

  useEffect(() => {
    Promise.all([
      getScenarios().catch(() => []),
      getIndianScenarios().catch(() => []),
      getProviders().catch(() => []),
      getHealth().catch(() => null),
      getResearchEvalData().catch(() => null),
    ])
      .then(([s, indS, p, h, ev]) => {
        setScenarios(Array.isArray(s) ? s : [])
        setIndianScenarios(Array.isArray(indS) ? indS : [])
        setProviders(Array.isArray(p) ? p : [])
        setHealth(h)
        setEvalData(ev)
      })
      .catch((e) => setError(e.message))
  }, [])

  const buildPayload = () => {
    const isCustom = scenario === CUSTOM_KEY
    return isCustom
      ? {
          provider,
          seed: Number(seed),
          profile: custom.profile,
          planned_meal: { items: custom.planned.map(toMealItem) },
          pantry: custom.pantry.map(toMealItem),
        }
      : { scenario, provider, seed: Number(seed) }
  }

  async function run() {
    setBusy(true)
    setError(null)
    const isCustom = scenario === CUSTOM_KEY
    const request = buildPayload()
    const safeScenarios = Array.isArray(scenarios) ? scenarios : []
    const safeIndianScenarios = Array.isArray(indianScenarios) ? indianScenarios : []
    const allKnown = [...safeScenarios, ...safeIndianScenarios]
    const label = isCustom
      ? 'Custom meal'
      : (allKnown.find((s) => s.key === scenario)?.title ?? scenario)
    try {
      const result = await recommend(request)
      setTrace(result)
      setRanWith({ scenario, provider, seed: Number(seed), label })
      setStage('stage2')
    } catch (e) {
      setError(e.message)
      setTrace(null)
      setRanWith(null)
    } finally {
      setBusy(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      await exportTrace(buildPayload())
    } catch (e) {
      setError(`Export failed: ${e.message}`)
    } finally {
      setExporting(false)
    }
  }

  const safeScenarios = Array.isArray(scenarios) ? scenarios : []
  const safeIndianScenarios = Array.isArray(indianScenarios) ? indianScenarios : []
  const allKnownScenarios = [...safeScenarios, ...safeIndianScenarios]
  const selected = allKnownScenarios.find((s) => s.key === scenario)
  const isCustom = scenario === CUSTOM_KEY

  const stale =
    ranWith !== null &&
    (ranWith.scenario !== scenario ||
      ranWith.provider !== provider ||
      ranWith.seed !== Number(seed))

  return (
    <div className="space-y-6">
      {/* Liveness probe and dataset status bar */}
      {health && (
        <div className="flex flex-wrap items-center justify-between text-slate-500 text-xs font-mono border-b border-stone-200/80 pb-2.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-forest-900">FoodSense Research Pipeline</span>
            <span>&middot;</span>
            <span>{health.n_foods.toLocaleString()} USDA foods</span>
            <span>&middot;</span>
            <span className="text-emerald-800 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
              {health.n_indian_foods?.toLocaleString() || 572} IFCT 2017 Indian foods
            </span>
            <span>&middot;</span>
            <span>{health.model_loaded ? 'LightGBM surrogate active' : 'Rule engine fallback'}</span>
          </div>
          <span className="text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            Offline First &middot; Provenance Grounded
          </span>
        </div>
      )}

      {/* Scenario & Controls Card */}
      <section className="bg-white border border-stone-200 rounded-xl p-5 shadow-sm space-y-4">
        <div className="grid md:grid-cols-[2fr_1fr_auto_auto] gap-3 items-end">
          <label className="block">
            <span className="text-xs uppercase tracking-wide font-bold text-forest-800">
              Research Scenario
            </span>
            <select
              className="mt-1 w-full border border-stone-300 rounded-lg px-2.5 py-2 text-sm bg-white"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
            >
              <optgroup label="Standard Research Scenarios">
                {safeScenarios.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.title}
                  </option>
                ))}
              </optgroup>
              {safeIndianScenarios.length > 0 && (
                <optgroup label="Indian Nutrition Scenarios (ICMR-NIN &amp; IFCT 2017)">
                  {safeIndianScenarios.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.title}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Custom Execution">
                <option value={CUSTOM_KEY}>Custom &mdash; build your own case</option>
              </optgroup>
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide font-bold text-forest-800">
              Stage-3 Provider
            </span>
            <select
              className="mt-1 w-full border border-stone-300 rounded-lg px-2.5 py-2 text-sm bg-white"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.available}>
                  {p.name}
                  {p.available ? (p.is_default ? ' (offline default)' : '') : ' — unavailable'}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs uppercase tracking-wide font-bold text-forest-800">DE Seed</span>
            <input
              type="number"
              min="0"
              className="mt-1 w-24 border border-stone-300 rounded-lg px-2.5 py-2 text-sm font-mono"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </label>

          <button
            type="button"
            onClick={run}
            disabled={busy || (isCustom && custom.planned.length === 0)}
            className="bg-forest-800 hover:bg-forest-900 text-white rounded-lg px-6 py-2.5 font-bold text-sm shadow-sm transition disabled:opacity-50"
          >
            {busy ? 'Optimizing…' : 'Run Pipeline'}
          </button>
        </div>

        {isCustom ? (
          <div className="mt-4 border-t border-stone-200 pt-4">
            <CustomBuilder value={custom} onChange={setCustom} />
            {custom.planned.length === 0 && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 mt-3">
                Add at least one food to the planned meal before running.
              </p>
            )}
          </div>
        ) : (
          selected && (
            <p className="text-sm text-stone-600 mt-3 border-l-2 border-forest-600 pl-3">
              {selected.description}
            </p>
          )
        )}

        {providers.some((p) => !p.available) && (
          <p className="text-xs text-stone-400 mt-2">
            {providers
              .filter((p) => !p.available)
              .map((p) => `${p.name}: ${p.reason}`)
              .join(' · ')}
          </p>
        )}
      </section>

      {error && (
        <div className="bg-rose-50 border border-rose-300 rounded-lg p-3 text-rose-900 text-xs">
          <strong>Request failed.</strong> {error}
        </div>
      )}

      {/* Primary Research Dashboard */}
      {trace && (
        <div className="space-y-6">
          {/* Active Run Banner with Quick Actions */}
          <div
            className={`rounded-xl border px-5 py-4 shadow-sm ${
              stale ? 'bg-amber-50 border-amber-300' : 'bg-white border-stone-200'
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] uppercase tracking-wide text-forest-700 font-bold bg-forest-50 px-2 py-0.5 rounded border border-forest-200">
                    Counterfactual Optimization Completed
                  </span>
                  <span className="text-xs text-stone-400 font-mono">
                    {(trace.total_runtime_s * 1000).toFixed(0)} ms total
                  </span>
                </div>
                <h2 className="font-extrabold text-stone-900 text-lg mt-1">{ranWith?.label}</h2>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={handleExport}
                  disabled={exporting}
                  className="bg-stone-100 hover:bg-stone-200 text-stone-700 text-xs font-semibold px-3 py-1.5 rounded-lg border border-stone-300 flex items-center gap-1.5 transition"
                >
                  <span>📥</span>
                  <span>{exporting ? 'Exporting…' : 'Export JSON Trace'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveVizTab('figures')}
                  className="bg-forest-800 hover:bg-forest-900 text-white text-xs font-bold px-3 py-1.5 rounded-lg shadow-sm flex items-center gap-1.5 transition"
                >
                  <span>📊</span>
                  <span>View Publication Figures</span>
                </button>
              </div>
            </div>
            {stale && (
              <p className="text-xs text-amber-900 mt-2">
                The scenario controls above have changed since this run. These results reflect{' '}
                <strong>{ranWith?.label}</strong> &mdash; press <em>Run Pipeline</em> to update.
              </p>
            )}
          </div>

          {/* Headline Summary Metrics */}
          <Metrics trace={trace} />

          {/* Meal Side-by-Side Comparison */}
          <MealSummarySideBySide
            plannedMeal={trace.planned_meal}
            counterfactualMeal={trace.counterfactual_meal || trace.stage2?.optimized_meal}
          />

          {/* Four-Stage Diagnostics Cards */}
          <FourStageDiagnosticsCards trace={trace} />

          {/* Detailed Ingredient Counterfactual Audit Table */}
          <IngredientChangeTable diff={trace.stage2?.diff || trace.diff} />

          {/* ----------------------------------------------------------------- */}
          {/* Interactive Research Visualization Suite (Tabs) */}
          {/* ----------------------------------------------------------------- */}
          <section className="bg-white border border-stone-200 rounded-xl p-5 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-stone-200 pb-3">
              <div>
                <h3 className="font-extrabold text-forest-950 text-base">
                  Interactive Research Visualizations &amp; Empirical Analytics
                </h3>
                <p className="text-xs text-stone-500">
                  Real-time SVG charts for nutrient repair, optimization convergence, verification auditing, and academic benchmarks.
                </p>
              </div>

              {/* Visualization Sub-Navigation */}
              <div className="flex items-center gap-1 bg-stone-100 p-1 rounded-xl border border-stone-200 overflow-x-auto">
                <button
                  type="button"
                  onClick={() => setActiveVizTab('nutrients')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition whitespace-nowrap ${
                    activeVizTab === 'nutrients'
                      ? 'bg-forest-800 text-white shadow-sm'
                      : 'text-stone-600 hover:text-stone-900'
                  }`}
                >
                  Nutrients &amp; Targets
                </button>
                <button
                  type="button"
                  onClick={() => setActiveVizTab('trajectory')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition whitespace-nowrap ${
                    activeVizTab === 'trajectory'
                      ? 'bg-forest-800 text-white shadow-sm'
                      : 'text-stone-600 hover:text-stone-900'
                  }`}
                >
                  Edits &amp; Search Trajectory
                </button>
                <button
                  type="button"
                  onClick={() => setActiveVizTab('verification')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition whitespace-nowrap ${
                    activeVizTab === 'verification'
                      ? 'bg-forest-800 text-white shadow-sm'
                      : 'text-stone-600 hover:text-stone-900'
                  }`}
                >
                  Verification &amp; Sources
                </button>
                <button
                  type="button"
                  onClick={() => setActiveVizTab('benchmarks')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition whitespace-nowrap ${
                    activeVizTab === 'benchmarks'
                      ? 'bg-forest-800 text-white shadow-sm'
                      : 'text-stone-600 hover:text-stone-900'
                  }`}
                >
                  Academic Benchmarks
                </button>
                <button
                  type="button"
                  onClick={() => setActiveVizTab('figures')}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition whitespace-nowrap ${
                    activeVizTab === 'figures'
                      ? 'bg-terracotta-500 text-white shadow-sm'
                      : 'text-stone-600 hover:text-stone-900'
                  }`}
                >
                  Publication Figures (IEEE)
                </button>
              </div>
            </div>

            {/* Tab 1: Nutrients and Target RDA */}
            {activeVizTab === 'nutrients' && (
              <div className="space-y-4">
                <NutrientComparisonChart trace={trace} />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <NutrientChangeChart trace={trace} />
                  <TargetVsAchievedChart trace={trace} />
                </div>
              </div>
            )}

            {/* Tab 2: Edits and Optimization Search Trajectory */}
            {activeVizTab === 'trajectory' && (
              <div className="space-y-4">
                <CounterfactualEditsChart trace={trace} />
                <ConvergenceTrajectoryChart trace={trace} />
              </div>
            )}

            {/* Tab 3: Verification Audit and Catalog Composition */}
            {activeVizTab === 'verification' && (
              <div className="space-y-4">
                <VerificationDiscrepancyChart trace={trace} />
                <FoodSourceCompositionChart trace={trace} />
              </div>
            )}

            {/* Tab 4: Empirical Research Benchmarks */}
            {activeVizTab === 'benchmarks' && (
              <div className="space-y-4">
                <AcademicBenchmarkCharts evalData={evalData} />
              </div>
            )}

            {/* Tab 5: Publication Figures and Vector Exports */}
            {activeVizTab === 'figures' && (
              <div className="space-y-4">
                <PublicationFigures trace={trace} />
              </div>
            )}
          </section>

          {/* Trace Warnings if any */}
          {trace.warnings?.length > 0 && (
            <div className="bg-amber-50 border border-amber-300 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-amber-900 mb-1">Pipeline Trace Warnings</h3>
              <ul className="text-xs text-amber-900 list-disc list-inside space-y-0.5">
                {trace.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Stepper with Stage-by-Stage Inspector */}
          <div className="space-y-3">
            <div className="text-xs font-bold text-stone-600 uppercase tracking-wide">
              Detailed Stage Telemetry Inspector
            </div>
            <Stepper trace={trace} active={stage} onSelect={setStage} />
            <section className="bg-white border border-stone-200 rounded-xl p-5 shadow-sm">
              <StagePanel stage={stage} trace={trace} />
            </section>
          </div>

          {/* Raw Verbatim Trace JSON Viewer */}
          <section className="bg-white border border-stone-200 rounded-xl shadow-sm">
            <button
              type="button"
              onClick={() => setShowJson((v) => !v)}
              className="w-full text-left px-5 py-3.5 font-bold text-stone-800 flex justify-between items-center text-xs"
            >
              <span>Verbatim PipelineTrace Response (JSON Contract)</span>
              <span className="text-stone-400 font-mono text-xs">
                seed {trace.seed} · {showJson ? '− Collapse' : '+ Expand'}
              </span>
            </button>
            {showJson && (
              <pre className="px-5 pb-5 text-[11px] overflow-x-auto text-stone-700 max-h-96 overflow-y-auto bg-stone-50 border-t border-stone-100 font-mono">
                {JSON.stringify(trace, null, 2)}
              </pre>
            )}
          </section>
        </div>
      )}

      {!trace && !error && (
        <div className="bg-white border border-stone-200 rounded-xl p-8 text-center space-y-3 shadow-sm">
          <div className="w-12 h-12 rounded-2xl bg-forest-50 border border-forest-200 flex items-center justify-center text-2xl mx-auto">
            🔬
          </div>
          <h3 className="text-base font-bold text-forest-900">
            Four-Stage Counterfactual Optimization &amp; Indian Nutrition Integration
          </h3>
          <p className="text-xs text-stone-600 max-w-xl mx-auto leading-relaxed">
            Select an academic scenario above or construct a custom meal to launch the full 4-stage pipeline:
            Stage 1 ML Suitability &rarr; Stage 2 Differential Evolution &rarr; Stage 3 Grounded Rationale &rarr; Stage 4 Independent Multi-Source Catalog Verification.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={run}
              disabled={busy}
              className="bg-forest-800 hover:bg-forest-900 text-white rounded-lg px-6 py-2.5 font-bold text-xs shadow-sm transition"
            >
              {busy ? 'Running…' : 'Run Pipeline on Toddler Scenario'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
