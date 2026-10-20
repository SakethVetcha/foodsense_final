// Tests for FoodSense 3-Page Flow & Preserved Pipeline

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import PipelinePage from './components/PipelinePage'

const SCENARIOS = [
  {
    key: 'toddler_choking',
    title: 'Toddler, 18 months: whole grapes and whole peanuts',
    description: 'A choking-hazard lunch.',
    age_group: 'toddler',
    goal: 'balanced_nutrition',
    health_flags: [],
    n_planned_items: 3,
    n_pantry_items: 8,
  },
]

const PROVIDERS = [
  { name: 'template', available: true, reason: '', is_default: true },
  { name: 'anthropic', available: false, reason: 'ANTHROPIC_API_KEY not set', is_default: false },
]

const HEALTH = {
  status: 'ok',
  version: '0.1.0',
  model_loaded: true,
  n_foods: 2590,
  n_indian_foods: 572,
  default_provider: 'template',
}

const LIFE_STAGES = [
  { key: 'child_5_6', label: 'Child (5–6 years)', min_age: 5, max_age: 6, sex_specific: false },
  { key: 'teen_13_15', label: 'Adolescent (13–15 years)', min_age: 13, max_age: 15, sex_specific: true },
]

const NUTRIENTS = (kcal, p, c, f, fib, fe) => ({
  energy_kcal: kcal,
  protein_g: p,
  carbohydrate_g: c,
  fat_g: f,
  fiber_g: fib,
  iron_mg: fe,
})

const MEAL = (slot, title) => ({
  slot,
  title,
  items: [
    {
      food_id: 'X001',
      name: `${title} dish`,
      category: 'prepared',
      quantity_g: 100,
      form: 'whole',
      is_dish: true,
      nutrients: NUTRIENTS(150, 5, 25, 4, 2, 1.2),
    },
  ],
  nutrients: NUTRIENTS(150, 5, 25, 4, 2, 1.2),
  energy_kcal: 150,
  energy_share_of_day: 0.25,
  macro_shares: { protein: 0.13, carbohydrate: 0.6, fat: 0.27 },
  compliance: 0.8,
  glycemic_load: 12,
  note: '',
})

const PLAN = {
  profile: {
    age_years: 13,
    sex: 'female',
    diet: 'vegetarian',
    activity: 'moderate',
    goal: 'balanced',
    height_cm: 155,
    weight_kg: 48,
    allergies: [],
    regional_preference: '',
  },
  life_stage: 'teen_13_15',
  life_stage_label: 'Adolescent (13–15 years)',
  sex: 'female',
  reference_weight_kg: 49.6,
  source: 'ICMR-NIN 2020, RDA for boys/girls 13-15 y',
  energy_target_kcal: 2400,
  meals: [
    MEAL('breakfast', 'Breakfast'),
    MEAL('lunch', 'Lunch'),
    MEAL('dinner', 'Dinner'),
    MEAL('snacks', 'Snacks'),
  ],
  day_nutrients: NUTRIENTS(2200, 60, 320, 70, 30, 29.5),
  day_macro_shares: { protein: 0.14, carbohydrate: 0.57, fat: 0.29 },
  day_glycemic_load: 120,
  day_compliance: 0.82,
  nutrient_table: [
    { key: 'energy_kcal', label: 'Energy', unit: 'kcal', target: 2400, actual: 2200, pct: 91.7, kind: 'band' },
    { key: 'protein_g', label: 'Protein', unit: 'g', target: 43, actual: 60, pct: 139.5, kind: 'floor' },
    { key: 'carbohydrate_g', label: 'Carbohydrate', unit: 'g', target: 305, actual: 320, pct: 104.9, kind: 'band' },
    { key: 'fat_g', label: 'Fat', unit: 'g', target: 74, actual: 70, pct: 94.6, kind: 'band' },
    { key: 'fiber_g', label: 'Dietary fibre', unit: 'g', target: 36, actual: 30, pct: 83.3, kind: 'floor' },
    { key: 'iron_mg', label: 'Iron', unit: 'mg', target: 30, actual: 29.5, pct: 98.3, kind: 'floor' },
  ],
  insights: ['Iron is at 98% of the daily RDA.'],
  warnings: ['Sodium excludes added cooking salt.'],
  verified: true,
  seed: 42,
  runtime_s: 0.01,
  lab_report: null,
}

const SAMPLE_INDIAN_FOODS = [
  {
    food_id: 'IF001',
    name: 'Roti (Whole Wheat Phulka)',
    category: 'staple',
    serving_size_g: 40,
    nutrients: NUTRIENTS(120, 3.5, 24, 0.8, 3.2, 1.4),
  },
  {
    food_id: 'IF002',
    name: 'Idli',
    category: 'prepared',
    serving_size_g: 80,
    nutrients: NUTRIENTS(130, 4.0, 26, 0.5, 1.8, 0.9),
  },
]

function stubFetch(overrides = {}) {
  const routes = {
    '/api/scenarios': SCENARIOS,
    '/api/providers': PROVIDERS,
    '/api/health': HEALTH,
    '/api/life-stages': LIFE_STAGES,
    '/api/indian-foods': SAMPLE_INDIAN_FOODS,
    ...overrides,
  }
  vi.stubGlobal(
    'fetch',
    vi.fn((url) =>
      Promise.resolve({
        ok: true,
        headers: { get: () => null },
        json: () => Promise.resolve(routes[url] ?? routes[String(url).split('?')[0]] ?? {}),
      }),
    ),
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('App shell and Page A (Home)', () => {
  it('renders the FoodSense branding, tagline, and navigation tabs', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText('FoodSense').length).toBeGreaterThan(0))
    expect(screen.getAllByText(/Eat smart\. Feel good\./i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /^home$/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^meal planner$/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^research pipeline$/i })).toBeTruthy()
  })

  it('renders the Indian food hero banner and category explorer', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText(/Build My Meal Plan/i).length).toBeGreaterThan(0))
    expect(screen.getByText(/Explore Indian Nutrition Database/i)).toBeTruthy()
    expect(screen.getByText('All Foods')).toBeTruthy()
    expect(screen.getByText('Breakfast')).toBeTruthy()
    expect(screen.getByText('Lunch')).toBeTruthy()
  })

  it('switches to the research pipeline on demand', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText(/Build My Meal Plan/i).length).toBeGreaterThan(0))
    fireEvent.click(screen.getByRole('button', { name: /^research pipeline$/i }))
    await waitFor(() => expect(screen.getByText(/Toddler, 18 months/)).toBeTruthy())
  })
})

describe('Page B (User Input Form)', () => {
  it('navigates from Home to Input Page when clicking Build My Meal Plan', async () => {
    stubFetch()
    render(<App />)
    await waitFor(() => expect(screen.getAllByText(/Build My Meal Plan/i).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByText(/Build My Meal Plan/i)[0])
    await waitFor(() => expect(screen.getByText(/Personal Nutritional Profile/i)).toBeTruthy())
    expect(screen.getByText(/Age \(5–20 Years\)/i)).toBeTruthy()
    expect(screen.getByText(/Biological Sex/i)).toBeTruthy()
    expect(screen.getByText(/Back to Home/i)).toBeTruthy()
  })

  it('shows life-stage label for chosen age', async () => {
    stubFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^meal planner$/i }))
    await waitFor(() => expect(screen.getByText(/Personal Nutritional Profile/i)).toBeTruthy())
    const ageInput = screen.getByLabelText(/Age \(5–20 Years\)/i)
    fireEvent.change(ageInput, { target: { value: '14' } })
    await waitFor(() => expect(screen.getByText(/Adolescent \(13–15 years\)/)).toBeTruthy())
  })

  it('rejects an invalid age outside 5-20 years', async () => {
    stubFetch()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^meal planner$/i }))
    await waitFor(() => expect(screen.getByText(/Personal Nutritional Profile/i)).toBeTruthy())
    const ageInput = screen.getByLabelText(/Age \(5–20 Years\)/i)
    fireEvent.change(ageInput, { target: { value: '25' } })
    await waitFor(() =>
      expect(screen.getByText(/Supported age range is 5 to 20 years/i)).toBeTruthy(),
    )
  })
})

describe('Page C (Results Dashboard)', () => {
  it('renders four meal cards and charts after generating plan', async () => {
    stubFetch({ '/api/plan': PLAN })
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^meal planner$/i }))
    await waitFor(() => expect(screen.getByText(/Personal Nutritional Profile/i)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /generate 4-meal plan/i }))
    await waitFor(() => expect(screen.getByText(/Adolescent \(13–15 years\)/)).toBeTruthy())
    for (const slot of ['Breakfast', 'Lunch', 'Dinner', 'Snacks']) {
      expect(screen.getByRole('heading', { name: slot })).toBeTruthy()
    }
    expect(screen.getAllByText(/IFCT 2017 Verified/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Interactive Graphical Analysis/i)).toBeTruthy()
    expect(screen.getByText(/Print \/ Save PDF/i)).toBeTruthy()
  })

  it('flags an API error if generation fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (String(url).includes('/api/plan')) {
          return Promise.resolve({
            ok: false,
            status: 422,
            headers: { get: () => null },
            json: () => Promise.resolve({ error: 'invalid_request', detail: 'Invalid parameters' }),
          })
        }
        return Promise.resolve({
          ok: true,
          headers: { get: () => null },
          json: () => Promise.resolve(url === '/api/life-stages' ? LIFE_STAGES : HEALTH),
        })
      }),
    )
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /^meal planner$/i }))
    await waitFor(() => expect(screen.getByText(/Personal Nutritional Profile/i)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /generate 4-meal plan/i }))
    await waitFor(() => expect(screen.getByText(/Request failed/i)).toBeTruthy())
  })
})

// ---------------------------------------------------------------------------
// The preserved four-stage pipeline
// ---------------------------------------------------------------------------

describe('PipelinePage', () => {
  it('populates the scenario dropdown from the API', async () => {
    stubFetch()
    render(<PipelinePage />)
    await waitFor(() => expect(screen.getByText(/Toddler, 18 months/)).toBeTruthy())
  })

  it('marks an unavailable provider and shows why', async () => {
    stubFetch()
    render(<PipelinePage />)
    await waitFor(() => {
      expect(screen.getByText(/anthropic — unavailable/)).toBeTruthy()
      expect(screen.getByText(/ANTHROPIC_API_KEY not set/)).toBeTruthy()
    })
  })

  it('offers a custom option in the scenario dropdown', async () => {
    stubFetch()
    render(<PipelinePage />)
    await waitFor(() => expect(screen.getByText(/build your own case/i)).toBeTruthy())
  })
})
