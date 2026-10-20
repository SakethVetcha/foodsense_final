import { useEffect, useState } from 'react'
import { searchIndianFoods } from '../../api'

const CATEGORIES = [
  { key: 'all', label: 'All Foods', icon: '🍲' },
  { key: 'breakfast', label: 'Breakfast', icon: '🥞', slot: 'breakfast' },
  { key: 'lunch', label: 'Lunch', icon: '🍛', slot: 'lunch' },
  { key: 'dinner', label: 'Dinner', icon: '🥘', slot: 'dinner' },
  { key: 'snacks', label: 'Snacks', icon: '🥟', slot: 'snacks' },
  { key: 'high_protein', label: 'High Protein', icon: '💪' },
  { key: 'high_fibre', label: 'High Fibre', icon: '🌾' },
]

export default function HomePage({ onStartPlanning, nFoods = 572 }) {
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [foods, setFoods] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)

    const slot = ['breakfast', 'lunch', 'dinner', 'snacks'].includes(selectedCategory)
      ? selectedCategory
      : ''

    searchIndianFoods({ q: searchQuery, slot, limit: 16 })
      .then((items) => {
        if (!active) return
        let filtered = items || []
        if (selectedCategory === 'high_protein') {
          filtered = [...filtered].sort(
            (a, b) => (b.nutrients?.protein_g || 0) - (a.nutrients?.protein_g || 0),
          )
        } else if (selectedCategory === 'high_fibre') {
          filtered = [...filtered].sort(
            (a, b) => (b.nutrients?.fiber_g || 0) - (a.nutrients?.fiber_g || 0),
          )
        }
        setFoods(filtered)
      })
      .catch(() => {
        if (active) setFoods([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [selectedCategory, searchQuery])

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-forest-800 via-forest-700 to-forest-600 text-white p-8 md:p-12 shadow-md border border-forest-600">
        <div className="relative z-10 max-w-2xl space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-forest-900/60 border border-forest-500/40 text-xs font-medium text-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            ICMR-NIN 2020 RDA &amp; IFCT 2017 Verified
          </div>

          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-white">
            FoodSense
          </h1>
          <p className="text-xl sm:text-2xl font-medium text-terracotta-200 tracking-wide">
            Eat smart. Feel good.
          </p>

          <p className="text-sm sm:text-base text-forest-100/90 leading-relaxed max-w-xl">
            A scientifically grounded Indian nutrition and meal planning system tailored for
            children and youth aged <strong>5 through 20 years</strong>. Get four balanced Indian
            meals with verified macronutrients, regional preferences, and interactive analysis.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={onStartPlanning}
              className="bg-terracotta-500 hover:bg-terracotta-600 active:bg-terracotta-700 text-white px-7 py-3.5 rounded-xl font-bold text-base shadow-lg transition-all transform hover:-translate-y-0.5 flex items-center gap-2"
            >
              <span>Build My Meal Plan</span>
              <span className="text-lg">→</span>
            </button>
            <span className="text-xs text-forest-200">
              No login required · Runs offline · {nFoods}+ Indian foods
            </span>
          </div>
        </div>

        {/* Decorative Indian spice & leaf pattern elements */}
        <div className="absolute right-0 bottom-0 translate-x-12 translate-y-12 w-80 h-80 rounded-full bg-emerald-400/10 blur-3xl pointer-events-none" />
        <div className="absolute right-8 top-1/2 -translate-y-1/2 hidden md:block opacity-20 pointer-events-none text-9xl">
          🌾
        </div>
      </section>

      {/* Value Pillars */}
      <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-stone-200/80 rounded-xl p-4 shadow-sm hover:border-forest-500/50 transition">
          <div className="w-10 h-10 rounded-lg bg-forest-50 text-forest-700 flex items-center justify-center font-bold text-lg mb-3">
            🎯
          </div>
          <h3 className="font-semibold text-slate-900 text-sm mb-1">Ages 5–20 Development</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Strictly tailored to pediatric and adolescent growth milestones with sex-specific iron
            and energy reference values.
          </p>
        </div>

        <div className="bg-white border border-stone-200/80 rounded-xl p-4 shadow-sm hover:border-forest-500/50 transition">
          <div className="w-10 h-10 rounded-lg bg-terracotta-50 text-terracotta-600 flex items-center justify-center font-bold text-lg mb-3">
            🍛
          </div>
          <h3 className="font-semibold text-slate-900 text-sm mb-1">Four Balanced Meals</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Personalized breakfast (25%), lunch (30%), dinner (30%), and healthy snacks (15%)
            optimized for sustained energy.
          </p>
        </div>

        <div className="bg-white border border-stone-200/80 rounded-xl p-4 shadow-sm hover:border-forest-500/50 transition">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold text-lg mb-3">
            🔬
          </div>
          <h3 className="font-semibold text-slate-900 text-sm mb-1">IFCT 2017 Verified</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Nutritional metrics extracted from the Indian Food Composition Tables (ICMR-NIN). No
            fabricated values.
          </p>
        </div>

        <div className="bg-white border border-stone-200/80 rounded-xl p-4 shadow-sm hover:border-forest-500/50 transition">
          <div className="w-10 h-10 rounded-lg bg-amber-50 text-amber-700 flex items-center justify-center font-bold text-lg mb-3">
            🛡️
          </div>
          <h3 className="font-semibold text-slate-900 text-sm mb-1">Safe &amp; Personalized</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Respects regional cuisines, vegetarian/eggetarian diets, food allergies (gluten, dairy,
            nuts), and dislikes.
          </p>
        </div>
      </section>

      {/* Indian Food Database Explorer */}
      <section className="bg-white border border-stone-200/80 rounded-2xl p-6 shadow-sm space-y-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Explore Indian Nutrition Database</h2>
            <p className="text-xs text-slate-500">
              Browse authentic Indian foods, traditional staples, dals, curries, and regional dishes
              with verified nutrient profiles.
            </p>
          </div>
          <div className="w-full md:w-72">
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search roti, dal, paneer, idli…"
                className="w-full bg-cream-50 border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-forest-500"
              />
              <span className="absolute left-3 top-2.5 text-slate-400 text-sm">🔍</span>
            </div>
          </div>
        </div>

        {/* Categories Bar */}
        <div className="flex flex-wrap gap-2 pb-2 border-b border-slate-100">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.key}
              type="button"
              onClick={() => setSelectedCategory(cat.key)}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium transition ${
                selectedCategory === cat.key
                  ? 'bg-forest-700 text-white shadow-sm'
                  : 'bg-cream-100 text-slate-700 hover:bg-cream-200'
              }`}
            >
              <span>{cat.icon}</span>
              <span>{cat.label}</span>
            </button>
          ))}
        </div>

        {/* Food Items Grid */}
        {loading ? (
          <div className="py-12 text-center text-sm text-slate-400">Loading verified foods…</div>
        ) : foods.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400">
            No foods found matching "{searchQuery}". Try a different keyword or category.
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {foods.map((food) => {
              const nut = food.nutrients || {}
              return (
                <div
                  key={food.food_id}
                  className="bg-cream-50/60 border border-stone-200/90 rounded-xl p-3 flex flex-col justify-between hover:border-forest-500/60 hover:shadow-sm transition"
                >
                  <div>
                    <div className="flex items-start justify-between gap-1 mb-1">
                      <h4
                        className="text-sm font-semibold text-slate-800 truncate"
                        title={food.name}
                      >
                        {food.name}
                      </h4>
                      <span className="text-[10px] text-forest-700 bg-forest-50 font-medium px-1.5 py-0.5 rounded">
                        {food.category}
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500">
                      Serving:{' '}
                      <span className="font-mono text-slate-700">
                        {food.serving_size_g ? `${food.serving_size_g} g` : '100 g'}
                      </span>
                    </div>
                  </div>

                  <div className="mt-2.5 pt-2 border-t border-slate-200/60 grid grid-cols-4 gap-1 text-center text-[10px]">
                    <div>
                      <span className="block font-bold text-slate-800">
                        {Math.round(nut.energy_kcal || 0)}
                      </span>
                      <span className="text-slate-400">kcal</span>
                    </div>
                    <div>
                      <span className="block font-bold text-forest-600">
                        {(nut.protein_g || 0).toFixed(1)}g
                      </span>
                      <span className="text-slate-400">protein</span>
                    </div>
                    <div>
                      <span className="block font-bold text-amber-600">
                        {(nut.carbohydrate_g || 0).toFixed(1)}g
                      </span>
                      <span className="text-slate-400">carbs</span>
                    </div>
                    <div>
                      <span className="block font-bold text-emerald-600">
                        {(nut.fiber_g || 0).toFixed(1)}g
                      </span>
                      <span className="text-slate-400">fibre</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        <div className="pt-2 flex justify-center">
          <button
            type="button"
            onClick={onStartPlanning}
            className="bg-forest-700 hover:bg-forest-800 text-white px-6 py-2.5 rounded-lg text-sm font-semibold shadow transition"
          >
            Ready to plan? Build My Meal Plan →
          </button>
        </div>
      </section>

      {/* Science & Methodology Disclaimer */}
      <section className="bg-cream-100 border border-stone-200 rounded-xl p-5 text-xs text-slate-600 space-y-2">
        <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
          Nutritional Methodology &amp; Reference Standards
        </h4>
        <p>
          FoodSense utilizes recommended dietary allowances (RDA) and estimated average requirements
          (EAR) defined by the <strong>ICMR-National Institute of Nutrition (2020)</strong> report for
          Indian children and adolescents. Food composition data is mapped from the verified{' '}
          <strong>Indian Food Composition Tables (IFCT 2017)</strong>.
        </p>
        <p className="text-slate-500">
          Disclaimer: This application provides nutritional planning and educational insights. It does
          not provide medical diagnoses or individual medical prescriptions.
        </p>
      </section>
    </div>
  )
}
