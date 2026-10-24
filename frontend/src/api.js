// Thin fetch layer. Same origin in the shipped shape -- FastAPI serves this
// bundle -- so these are relative paths with no base URL and no CORS.

/** Read the one error shape the API emits, or invent a readable one. */
async function unwrap(response) {
  if (response.ok) return response.json()
  let detail = `HTTP ${response.status}`
  try {
    const body = await response.json()
    detail = body.detail || body.error || detail
  } catch {
    // A non-JSON error body is itself the useful signal; keep the status.
  }
  const error = new Error(detail)
  error.status = response.status
  throw error
}

export const getHealth = () => fetch('/api/health').then(unwrap)
export const getScenarios = () => fetch('/api/scenarios').then(unwrap)
export const getIndianScenarios = () => fetch('/api/indian-scenarios').then(unwrap)
export const getProviders = () => fetch('/api/providers').then(unwrap)

/** Type-ahead over the unified food database (USDA + IFCT 2017 + Composite dishes). */
export const searchFoods = (q, limit = 10, source = '') => {
  const params = new URLSearchParams({ q, limit })
  if (source) params.set('source', source)
  return fetch(`/api/foods?${params.toString()}`).then(unwrap)
}

/**
 * Run the pipeline. `body` is either {scenario} or {profile, planned_meal, pantry}.
 * A provider with no key is NOT an error here -- it comes back 200 with
 * stage3.fallback_used set, and the UI badges it.
 */
export const recommend = (body) =>
  fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(unwrap)

/** Download full research pipeline trace as a reproducible JSON file. */
export const exportTrace = async (body) => {
  const res = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`Export failed: ${res.statusText}`)
  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `foodsense_trace_${body.scenario || 'custom'}.json`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

// ---------------------------------------------------------------------------
// Indian meal planner (ages 5-20)
// ---------------------------------------------------------------------------

/** The ICMR-NIN 2020 age bands, for the age selector. */
export const getLifeStages = () => fetch('/api/life-stages').then(unwrap)

/** Search the Indian food database for the "add a food you like" picker. */
export const searchIndianFoods = ({ q = '', slot = '', diet = '', limit = 20 } = {}) => {
  const params = new URLSearchParams({ q, limit })
  if (slot) params.set('slot', slot)
  if (diet) params.set('diet', diet)
  return fetch(`/api/indian-foods?${params.toString()}`).then(unwrap)
}

/**
 * Build a personalised day plan. The response is a `MealPlan`; nothing is
 * stored server-side and the response is marked no-store.
 */
export const createPlan = (body) =>
  fetch('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(unwrap)

/**
 * Interpret pasted lab values or base64 PDF into non-diagnostic dietary findings.
 * Sent to the server only for the duration of the request; never stored.
 */
export const analyseLabReport = (arg1, arg2) => {
  let body
  if (typeof arg1 === 'object' && arg1 !== null) {
    body = { text: arg1.text || '', pdf_base64: arg1.pdf_base64 || null, sex: arg1.sex || null }
  } else {
    body = { text: arg1 || '', pdf_base64: null, sex: arg2 || null }
  }
  return fetch('/api/lab-report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(unwrap)
}

/** Get suitable alternative Indian foods for replacement in a meal. */
export const getFoodAlternatives = ({ slot = '', diet = '', currentId = '', limit = 12 } = {}) => {
  const params = new URLSearchParams({ limit })
  if (slot) params.set('slot', slot)
  if (diet) params.set('diet', diet)
  if (currentId) params.set('current_id', currentId)
  return fetch(`/api/food-alternatives?${params.toString()}`).then(unwrap)
}

/** Recalculate nutrient totals and compliance for modified meals. */
export const recalculatePlan = ({ profile, meals, seed = 42 }) =>
  fetch('/api/recalculate-plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, meals, seed }),
  }).then(unwrap)

/** Compute BMI, Indian pediatric percentile category, and ICMR-NIN BMR. */
export const getBodyMetrics = ({ age_years, sex, height_cm, weight_kg }) =>
  fetch('/api/body-metrics', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ age_years, sex, height_cm, weight_kg }),
  }).then(unwrap)

// ---------------------------------------------------------------------------
// Academic Research Evaluation, Publication Figures & Data Exports
// ---------------------------------------------------------------------------

/** Get publication figure manifest and metadata. */
export const getResearchFigures = () => fetch('/api/research/figures').then(unwrap)

/** Regenerate publication-ready figures (300-DPI PNGs, vector SVGs, paired CSVs). */
export const generateResearchFigures = (trace = null) =>
  fetch('/api/research/generate-figures', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(trace ? { trace } : {}),
  }).then(unwrap)

/** Fetch empirical research evaluation datasets (baselines, lambda sweep, calibration). */
export const getResearchEvalData = () => fetch('/api/research/eval-data').then(unwrap)

/** Return the download URL for any generated figure, vector SVG, CSV, or ZIP. */
export const getFigureDownloadUrl = (filename) =>
  `/api/research/download-figure/${encodeURIComponent(filename)}`

