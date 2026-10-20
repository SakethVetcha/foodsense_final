import { useEffect, useState } from 'react'
import { getFoodAlternatives, recalculatePlan, searchIndianFoods } from '../../api'
import {
  EnergyByMeal,
  MACRO_COLORS,
  MacroDonut,
  MealMacroBars,
  NutrientAchievement,
  NutrientRadar,
} from './charts'
import LabFindings from './LabFindings'

function Card({ title, subtitle, children, tag }) {
  return (
    <section className="bg-white border border-stone-200/90 rounded-2xl p-5 shadow-sm space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-bold text-slate-900 text-sm">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        {tag && <span className="text-[11px] text-slate-400 font-mono">{tag}</span>}
      </div>
      {children}
    </section>
  )
}

function Kpi({ label, value, sub, tone = 'plain' }) {
  const tones = {
    plain: 'text-slate-900',
    good: 'text-forest-700',
    warn: 'text-terracotta-600',
    amber: 'text-amber-700',
  }
  return (
    <div className="px-4 py-3 flex flex-col justify-center">
      <div className="text-[10px] uppercase font-bold tracking-wider text-slate-500">{label}</div>
      <div className={`text-xl font-extrabold ${tones[tone]}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 truncate">{sub}</div>}
    </div>
  )
}

/** Item Replacement & Add Modal */
function FoodPickerModal({
  isOpen,
  title,
  slot,
  diet,
  currentFoodId,
  onSelect,
  onClose,
}) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')

  useEffect(() => {
    if (!isOpen) return
    setLoading(true)
    getFoodAlternatives({ slot, diet, currentId: currentFoodId, limit: 12 })
      .then((data) => setItems(data || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [isOpen, slot, diet, currentFoodId])

  if (!isOpen) return null

  const handleSearch = (q) => {
    setSearch(q)
    setLoading(true)
    searchIndianFoods({ q, slot, diet, limit: 12 })
      .then((data) => setItems(data || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-slate-900 text-base">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-lg font-bold"
          >
            ✕
          </button>
        </div>

        <div className="relative">
          <input
            type="text"
            value={search}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder={`Search Indian ${slot} alternatives…`}
            className="w-full bg-cream-50 border border-slate-300 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-forest-500"
          />
          <span className="absolute left-2.5 top-2 text-slate-400 text-xs">🔍</span>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {loading ? (
            <div className="py-8 text-center text-xs text-slate-400">Loading alternatives…</div>
          ) : items.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">No alternatives found.</div>
          ) : (
            items.map((food) => {
              const nut = food.nutrients_per_100g || food.nutrients || {}
              return (
                <div
                  key={food.food_id}
                  className="border border-stone-200 rounded-xl p-3 flex items-center justify-between hover:border-forest-500/60 hover:bg-forest-50/20 transition cursor-pointer"
                  onClick={() => onSelect(food)}
                >
                  <div className="max-w-[70%]">
                    <h4 className="text-xs font-bold text-slate-900">{food.name}</h4>
                    <span className="text-[10px] text-slate-500">
                      Category: {food.category} · Serving: {food.serving_size_g || 100}g
                    </span>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-600">
                      <span>{Math.round(nut.energy_kcal || 0)} kcal</span>
                      <span>·</span>
                      <span className="text-forest-700 font-semibold">
                        {(nut.protein_g || 0).toFixed(1)}g P
                      </span>
                      <span>·</span>
                      <span className="text-amber-700">{(nut.carbohydrate_g || 0).toFixed(1)}g C</span>
                      <span>·</span>
                      <span className="text-emerald-700 font-medium">
                        {(nut.fiber_g || 0).toFixed(1)}g Fib
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="bg-forest-700 hover:bg-forest-800 text-white px-3 py-1.5 rounded-lg text-xs font-semibold shadow-sm"
                  >
                    Select
                  </button>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

export default function PlanDashboard({ plan: initialPlan, onBack, onRegenerate }) {
  const [currentPlan, setCurrentPlan] = useState(initialPlan)
  const [recalculating, setRecalculating] = useState(false)
  const [modalConfig, setModalConfig] = useState({ isOpen: false })
  const [showJson, setShowJson] = useState(false)

  useEffect(() => {
    setCurrentPlan(initialPlan)
  }, [initialPlan])

  const n = currentPlan.day_nutrients
  const p = currentPlan.profile

  async function triggerRecalculate(updatedMeals) {
    setRecalculating(true)
    try {
      const recalculated = await recalculatePlan({
        profile: currentPlan.profile,
        meals: updatedMeals,
        seed: currentPlan.seed || 42,
      })
      setCurrentPlan(recalculated)
    } catch (e) {
      console.error('Failed to recalculate meal plan:', e)
    } finally {
      setRecalculating(false)
    }
  }

  function handleQuantityChange(mealIndex, itemIndex, newQuantity) {
    const qty = Math.max(5, Math.round(newQuantity))
    const updatedMeals = JSON.parse(JSON.stringify(currentPlan.meals))
    updatedMeals[mealIndex].items[itemIndex].quantity_g = qty
    triggerRecalculate(updatedMeals)
  }

  function handleRemoveItem(mealIndex, itemIndex) {
    const updatedMeals = JSON.parse(JSON.stringify(currentPlan.meals))
    if (updatedMeals[mealIndex].items.length <= 1) {
      alert('A meal must contain at least one item.')
      return
    }
    updatedMeals[mealIndex].items.splice(itemIndex, 1)
    triggerRecalculate(updatedMeals)
  }

  function openSwapModal(mealIndex, itemIndex) {
    const meal = currentPlan.meals[mealIndex]
    const item = meal.items[itemIndex]
    setModalConfig({
      isOpen: true,
      title: `Swap "${item.name}" with Alternative`,
      slot: meal.slot,
      diet: currentPlan.profile.diet,
      currentFoodId: item.food_id,
      onSelect: (newFood) => {
        const updatedMeals = JSON.parse(JSON.stringify(currentPlan.meals))
        updatedMeals[mealIndex].items[itemIndex] = {
          food_id: newFood.food_id,
          name: newFood.name,
          category: newFood.category,
          quantity_g: newFood.serving_size_g || item.quantity_g || 100,
          form: 'whole',
          is_dish: newFood.category === 'prepared',
          nutrients: newFood.nutrients_per_100g || newFood.nutrients,
        }
        setModalConfig({ isOpen: false })
        triggerRecalculate(updatedMeals)
      },
    })
  }

  function openAddModal(mealIndex) {
    const meal = currentPlan.meals[mealIndex]
    setModalConfig({
      isOpen: true,
      title: `Add Food to ${meal.title}`,
      slot: meal.slot,
      diet: currentPlan.profile.diet,
      currentFoodId: '',
      onSelect: (newFood) => {
        const updatedMeals = JSON.parse(JSON.stringify(currentPlan.meals))
        updatedMeals[mealIndex].items.push({
          food_id: newFood.food_id,
          name: newFood.name,
          category: newFood.category,
          quantity_g: newFood.serving_size_g || 100,
          form: 'whole',
          is_dish: newFood.category === 'prepared',
          nutrients: newFood.nutrients_per_100g || newFood.nutrients,
        })
        setModalConfig({ isOpen: false })
        triggerRecalculate(updatedMeals)
      },
    })
  }

  const ironTarget =
    currentPlan.nutrient_table.find((r) => r.key === 'iron_mg')?.target || 1
  const ironTone = n.iron_mg / ironTarget >= 0.9 ? 'good' : 'warn'

  return (
    <div className="space-y-6 max-w-6xl mx-auto print-page">
      {/* Top Controls & Navigation Bar */}
      <div className="bg-white border border-stone-200/90 rounded-2xl p-5 shadow-sm no-print">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onBack}
                className="text-xs font-semibold text-forest-700 hover:text-forest-800 bg-cream-50 border border-stone-200 px-3 py-1.5 rounded-lg transition"
              >
                ← Edit Inputs
              </button>
              <h2 className="text-lg font-bold text-slate-900">
                {currentPlan.life_stage_label} ({currentPlan.sex === 'female' ? 'Female' : 'Male'})
              </h2>
              {currentPlan.verified && (
                <span className="inline-flex items-center gap-1 bg-emerald-50 text-emerald-800 border border-emerald-300 rounded-full px-2.5 py-0.5 text-xs font-semibold">
                  ✓ IFCT 2017 Verified
                </span>
              )}
            </div>
            <p className="text-xs text-slate-600">
              Age {p.age_years} · {p.diet.replace('_', ' ')} · {p.activity} activity
              {p.regional_preference
                ? ` · ${p.regional_preference.replace('_', ' ')}`
                : ''}
              {p.allergies?.length > 0
                ? ` · Excluded: ${p.allergies.join(', ')}`
                : ''}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {recalculating && (
              <span className="text-xs text-forest-700 font-medium animate-pulse flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-forest-600"></span> Recalculating…
              </span>
            )}
            <button
              type="button"
              onClick={onRegenerate}
              className="bg-cream-100 hover:bg-cream-200 text-slate-800 border border-slate-300 text-xs font-semibold px-3.5 py-2 rounded-lg transition"
            >
              🔄 Regenerate Plan
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="bg-forest-700 hover:bg-forest-800 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition"
            >
              🖨️ Print / Save PDF
            </button>
          </div>
        </div>
      </div>

      {/* Daily Nutritional Summary KPIs */}
      <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-y sm:divide-y-0 sm:divide-x divide-stone-200 border border-stone-200/90 rounded-2xl bg-white shadow-sm overflow-hidden">
        <Kpi
          label="Daily Energy"
          value={`${Math.round(n.energy_kcal)} kcal`}
          sub={`Target: ${Math.round(currentPlan.energy_target_kcal)} kcal`}
        />
        <Kpi
          label="Protein"
          value={`${n.protein_g.toFixed(1)} g`}
          sub={`${(currentPlan.day_macro_shares.protein * 100).toFixed(0)}% of energy`}
          tone="good"
        />
        <Kpi
          label="Carbohydrates"
          value={`${n.carbohydrate_g.toFixed(0)} g`}
          sub={`${(currentPlan.day_macro_shares.carbohydrate * 100).toFixed(0)}% of energy`}
        />
        <Kpi
          label="Dietary Fibre"
          value={`${n.fiber_g.toFixed(1)} g`}
          sub="Adequate daily intake"
          tone="good"
        />
        <Kpi
          label="Total Fat"
          value={`${n.fat_g.toFixed(1)} g`}
          sub={`${(currentPlan.day_macro_shares.fat * 100).toFixed(0)}% of energy`}
        />
        <Kpi
          label="Iron (Fe)"
          value={`${n.iron_mg.toFixed(1)} mg`}
          sub={`ICMR-NIN RDA: ${ironTarget} mg`}
          tone={ironTone}
        />
      </section>

      {/* 4 Separate Meal Category Cards */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900">
              Personalized 4-Meal Plan
            </h3>
            <p className="text-xs text-slate-500">
              Breakfast (25%), Lunch (30%), Dinner (30%), Snacks (15%). Adjust serving sizes or swap
              dishes with suitable alternatives.
            </p>
          </div>
          <span className="text-xs text-forest-700 font-semibold bg-forest-50 px-2.5 py-1 rounded-full border border-forest-200">
            Click quantity or "Swap" to customize
          </span>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          {currentPlan.meals.map((meal, mealIdx) => {
            const mn = meal.nutrients
            return (
              <div
                key={meal.slot}
                className="bg-white border border-stone-200/90 rounded-2xl p-5 shadow-sm flex flex-col justify-between hover:border-forest-500/40 transition"
              >
                <div>
                  <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">
                        {meal.slot === 'breakfast'
                          ? '🥞'
                          : meal.slot === 'lunch'
                          ? '🍛'
                          : meal.slot === 'dinner'
                          ? '🥘'
                          : '🥟'}
                      </span>
                      <div>
                        <h4 className="font-bold text-slate-900 text-sm">{meal.title}</h4>
                        <span className="text-[11px] text-slate-500">
                          {Math.round(meal.energy_share_of_day * 100)}% of day · Compliance{' '}
                          {(meal.compliance * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-extrabold text-forest-700">
                        {Math.round(meal.energy_kcal)} kcal
                      </span>
                    </div>
                  </div>

                  {/* Food Items in this Meal */}
                  <ul className="divide-y divide-slate-100 my-3">
                    {meal.items.map((item, itemIdx) => (
                      <li
                        key={`${item.food_id}-${itemIdx}`}
                        className="py-2.5 flex items-center justify-between gap-2"
                      >
                        <div className="min-w-0 max-w-[55%]">
                          <span
                            className="text-xs font-semibold text-slate-800 block truncate"
                            title={item.name}
                          >
                            {item.name}
                          </span>
                          <span className="text-[10px] text-slate-400">
                            {Math.round(item.nutrients.energy_kcal)} kcal ·{' '}
                            {item.nutrients.protein_g.toFixed(1)}g P ·{' '}
                            {item.nutrients.carbohydrate_g.toFixed(1)}g C ·{' '}
                            {item.nutrients.fiber_g.toFixed(1)}g Fib
                          </span>
                        </div>

                        {/* Controls: Quantity + Swap + Remove */}
                        <div className="flex items-center gap-1.5 no-print">
                          {/* Serving Size Quantity Control */}
                          <div className="flex items-center border border-slate-200 rounded-lg overflow-hidden bg-cream-50">
                            <button
                              type="button"
                              onClick={() =>
                                handleQuantityChange(
                                  mealIdx,
                                  itemIdx,
                                  item.quantity_g - 10,
                                )
                              }
                              className="px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200 font-bold"
                            >
                              -
                            </button>
                            <span className="px-2 py-0.5 text-xs font-mono font-medium text-slate-800">
                              {Math.round(item.quantity_g)}g
                            </span>
                            <button
                              type="button"
                              onClick={() =>
                                handleQuantityChange(
                                  mealIdx,
                                  itemIdx,
                                  item.quantity_g + 10,
                                )
                              }
                              className="px-2 py-0.5 text-xs text-slate-600 hover:bg-slate-200 font-bold"
                            >
                              +
                            </button>
                          </div>

                          {/* Swap button */}
                          <button
                            type="button"
                            onClick={() => openSwapModal(mealIdx, itemIdx)}
                            className="text-[11px] font-semibold text-terracotta-600 hover:text-terracotta-700 bg-terracotta-50 hover:bg-terracotta-100 border border-terracotta-200 px-2 py-1 rounded-md transition"
                            title="Replace with alternative Indian dish"
                          >
                            Swap
                          </button>

                          {/* Delete button */}
                          <button
                            type="button"
                            onClick={() => handleRemoveItem(mealIdx, itemIdx)}
                            className="text-[11px] text-slate-400 hover:text-rose-600 px-1 py-1"
                            title="Remove item"
                          >
                            ✕
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <div className="pt-2 flex justify-between items-center no-print">
                    <button
                      type="button"
                      onClick={() => openAddModal(mealIdx)}
                      className="text-xs text-forest-700 hover:text-forest-800 font-semibold"
                    >
                      + Add food item
                    </button>
                  </div>

                  {/* Meal Nutrient Totals Row */}
                  <div className="mt-3 pt-3 border-t border-slate-100 grid grid-cols-4 gap-1 text-center text-xs bg-cream-50/50 rounded-xl py-1.5">
                    <div>
                      <span className="block font-bold text-forest-700">
                        {mn.protein_g.toFixed(1)} g
                      </span>
                      <span className="text-[10px] text-slate-400">Protein</span>
                    </div>
                    <div>
                      <span className="block font-bold text-amber-600">
                        {mn.carbohydrate_g.toFixed(1)} g
                      </span>
                      <span className="text-[10px] text-slate-400">Carbs</span>
                    </div>
                    <div>
                      <span className="block font-bold text-terracotta-600">
                        {mn.fat_g.toFixed(1)} g
                      </span>
                      <span className="text-[10px] text-slate-400">Fat</span>
                    </div>
                    <div>
                      <span className="block font-bold text-emerald-700">
                        {mn.fiber_g.toFixed(1)} g
                      </span>
                      <span className="text-[10px] text-slate-400">Fibre</span>
                    </div>
                  </div>
                  {meal.note && (
                    <p className="text-[11px] text-slate-400 mt-2 italic">{meal.note}</p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Graphical Analysis Dashboard (Requirement 5) */}
      <section className="space-y-4">
        <div>
          <h3 className="text-base font-bold text-slate-900">
            Interactive Graphical Analysis
          </h3>
          <p className="text-xs text-slate-500">
            Real-time visualization calculated from current meals and quantities. Updates
            dynamically when you adjust servings or swap dishes.
          </p>
        </div>

        {/* Charts Grid: 3-column top row */}
        <div className="grid lg:grid-cols-3 gap-4">
          <Card
            title="Meal-Wise Calorie Comparison"
            subtitle="Planned vs ICMR-NIN RDA slot targets"
          >
            <EnergyByMeal
              meals={currentPlan.meals}
              energyTarget={currentPlan.energy_target_kcal}
            />
          </Card>

          <Card
            title="Macronutrient Energy Distribution"
            subtitle="Protein, Carbs, and Fat share of energy"
          >
            <MacroDonut shares={currentPlan.day_macro_shares} />
          </Card>

          <Card
            title="Micronutrient Coverage Radar"
            subtitle="% of key minerals & vitamins achieved"
          >
            <NutrientRadar rows={currentPlan.nutrient_table} />
          </Card>
        </div>

        {/* Charts Grid: 2-column second row */}
        <div className="grid lg:grid-cols-2 gap-4">
          <Card
            title="Macronutrients & Fibre by Meal"
            subtitle="Grams of protein, carbs, fat, and dietary fibre per meal"
          >
            <MealMacroBars meals={currentPlan.meals} />
          </Card>

          <Card
            title="Nutrient Intake vs Reference Values"
            subtitle="Daily totals as a percentage of ICMR-NIN targets"
          >
            <NutrientAchievement rows={currentPlan.nutrient_table} />
          </Card>
        </div>
      </section>

      {/* Full Nutrient Proportions Table (Requirement 7) */}
      <section className="bg-white border border-stone-200/90 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Complete Nutritional Composition Table
            </h3>
            <p className="text-xs text-slate-500">
              Verified nutritional metrics grounded in IFCT 2017 with daily reference comparison.
            </p>
          </div>
          <span className="text-xs text-slate-500 font-mono">
            Glycemic Load: {currentPlan.day_glycemic_load}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-left text-slate-500 uppercase tracking-wider">
                <th className="py-2">Nutrient</th>
                <th className="py-2 text-right">Planned Total</th>
                <th className="py-2 text-right">Reference Target</th>
                <th className="py-2 pl-6">Coverage / Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {currentPlan.nutrient_table.map((r) => {
                const pct = r.pct == null ? null : Math.round(r.pct)
                const inBand =
                  r.band_low != null && r.band_high != null
                    ? r.actual >= r.band_low && r.actual <= r.band_high
                    : null
                const good =
                  pct == null
                    ? false
                    : r.kind === 'ceiling'
                    ? pct <= 100
                    : r.kind === 'band'
                    ? inBand !== false
                    : pct >= 90
                const targetText =
                  r.band_low != null && r.band_high != null
                    ? `${r.band_low}–${r.band_high}`
                    : (r.target ?? '—')

                return (
                  <tr key={r.key} className="hover:bg-cream-50/40">
                    <td className="py-2 font-medium text-slate-800">{r.label}</td>
                    <td className="py-2 text-right font-mono text-slate-900 font-bold">
                      {r.actual} {r.unit}
                    </td>
                    <td className="py-2 text-right font-mono text-slate-500">
                      {targetText} {r.unit}
                    </td>
                    <td className="py-2 pl-6">
                      <div className="flex items-center gap-3">
                        <div className="flex-1 h-2 rounded bg-slate-100 overflow-hidden max-w-xs">
                          <div
                            className={`h-full ${
                              good ? 'bg-forest-600' : 'bg-terracotta-500'
                            }`}
                            style={{ width: `${Math.min(pct ?? 0, 100)}%` }}
                          />
                        </div>
                        <span className="text-[11px] font-mono text-slate-600 w-16 text-right">
                          {r.kind === 'band' && r.band_low != null
                            ? inBand
                              ? 'In range'
                              : 'Outside'
                            : pct == null
                            ? '—'
                            : `${pct}%`}
                        </span>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Lab Findings if present */}
      {currentPlan.lab_report && <LabFindings report={currentPlan.lab_report} />}

      {/* Nutritional Insights & Explanations */}
      {currentPlan.insights?.length > 0 && (
        <section className="bg-forest-50/70 border border-forest-200 rounded-2xl p-5 space-y-2">
          <h4 className="text-xs font-bold text-forest-900 uppercase tracking-wider">
            Nutritional Rationale &amp; Explanations
          </h4>
          <ul className="text-xs text-forest-900 space-y-1 list-disc list-inside leading-relaxed">
            {currentPlan.insights.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Warnings & Notes */}
      {currentPlan.warnings?.length > 0 && (
        <section className="bg-cream-100 border border-stone-200 rounded-2xl p-5 space-y-2">
          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
            Guidelines, Assumptions &amp; Limitations
          </h4>
          <ul className="text-xs text-slate-600 space-y-1 list-disc list-inside leading-relaxed">
            {currentPlan.warnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Raw JSON Inspector */}
      <div className="bg-white border border-stone-200 rounded-2xl no-print overflow-hidden">
        <button
          type="button"
          onClick={() => setShowJson((v) => !v)}
          className="w-full text-left px-5 py-3 font-semibold text-xs text-slate-700 flex justify-between items-center"
        >
          <span>Raw Plan Data &amp; Nutrient Vectors</span>
          <span className="text-slate-400 font-mono text-xs">{showJson ? '▲ Hide' : '▼ Show'}</span>
        </button>
        {showJson && (
          <pre className="px-5 pb-5 text-[11px] overflow-x-auto text-slate-700 max-h-96 overflow-y-auto bg-slate-50 font-mono">
            {JSON.stringify(currentPlan, null, 2)}
          </pre>
        )}
      </div>

      {/* Alternative Food Replacement Modal */}
      <FoodPickerModal
        isOpen={modalConfig.isOpen}
        title={modalConfig.title}
        slot={modalConfig.slot}
        diet={modalConfig.diet}
        currentFoodId={modalConfig.currentFoodId}
        onSelect={modalConfig.onSelect}
        onClose={() => setModalConfig({ isOpen: false })}
      />
    </div>
  )
}
