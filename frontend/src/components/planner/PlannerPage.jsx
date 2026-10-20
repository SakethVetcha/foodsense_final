import { useEffect, useState } from 'react'
import { createPlan, getHealth, getLifeStages } from '../../api'
import HomePage from './HomePage'
import PlanDashboard from './PlanDashboard'
import PlannerForm from './PlannerForm'

// Three-page flow satisfying Requirement 8:
// Page A: HomePage (Hero banner, "Eat smart. Feel good.", food category explorer, "Build My Meal Plan" CTA)
// Page B: PlannerForm (Age 5-20, sex, height/weight, activity, diet, regional, allergies, likes/dislikes, lab upload)
// Page C: PlanDashboard (4 meal categories, serving size adjustment, food swapping, recalculation, dynamic charts)

const DEFAULT_PROFILE = {
  age_years: 13,
  sex: 'female',
  height_cm: null,
  weight_kg: null,
  activity: 'moderate',
  diet: 'vegetarian',
  regional_preference: '',
  allergies: [],
  likes: [],
  dislikes: [],
  goal: 'balanced',
  health_flags: [],
  exclude_tags: [],
  lab_text: null,
}

export default function PlannerPage({ initialView = 'home' }) {
  const [profile, setProfile] = useState(DEFAULT_PROFILE)
  const [lifeStages, setLifeStages] = useState([])
  const [health, setHealth] = useState(null)
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [view, setView] = useState(initialView)
  const [seed, setSeed] = useState(42)

  useEffect(() => {
    Promise.all([getLifeStages(), getHealth()])
      .then(([stages, h]) => {
        setLifeStages(stages)
        setHealth(h)
      })
      .catch((e) => setError(e.message))
  }, [])

  async function generate(customSeed) {
    setBusy(true)
    setError(null)
    const useSeed = customSeed !== undefined ? customSeed : seed
    try {
      const result = await createPlan({ ...profile, seed: useSeed })
      setPlan(result)
      setView('results')
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  function handleRegenerate() {
    const nextSeed = (seed + 17) % 1000
    setSeed(nextSeed)
    generate(nextSeed)
  }

  return (
    <div className="space-y-5">
      {health && health.n_indian_foods === 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-3 text-sm text-amber-900">
          The Indian food database is not built. Run{' '}
          <span className="font-mono">python -m foodsense.data.build_indian_food_db</span>.
        </div>
      )}

      {error && (
        <div className="bg-rose-50 border border-rose-300 rounded-lg p-3 text-rose-900 text-sm">
          <strong>Request failed.</strong> {error}
        </div>
      )}

      {/* Page A: Homepage */}
      {view === 'home' && (
        <HomePage
          onStartPlanning={() => {
            setView('input')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
          nFoods={health?.n_indian_foods || 572}
        />
      )}

      {/* Page B: User Input Page */}
      {view === 'input' && (
        <PlannerForm
          profile={profile}
          onChange={setProfile}
          onGenerate={() => generate()}
          onBackToHome={() => {
            setView('home')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
          busy={busy}
          lifeStages={lifeStages}
        />
      )}

      {/* Page C: Results Dashboard */}
      {view === 'results' && plan && (
        <PlanDashboard
          plan={plan}
          onBack={() => {
            setView('input')
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }}
          onRegenerate={handleRegenerate}
        />
      )}
    </div>
  )
}
