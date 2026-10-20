import { useState } from 'react'
import PipelinePage from './components/PipelinePage'
import PlannerPage from './components/planner/PlannerPage'

// Three-page primary flow:
// Page A: Home (Brand hero, "Eat smart. Feel good.", food category explorer)
// Page B: User Input Page (Age 5-20, sex, height/weight, preferences, allergies, lab report)
// Page C: Results Dashboard (4 meals, serving adjustments, food swap, recalculation, dynamic charts)
// + Preserved Research Pipeline tab for academic benchmark continuity.

const TABS = [
  { key: 'home', label: 'Home' },
  { key: 'planner', label: 'Meal Planner' },
  { key: 'pipeline', label: 'Research Pipeline' },
]

export default function App() {
  const [activeTab, setActiveTab] = useState('home')

  return (
    <div className="min-h-screen bg-cream-100 text-slate-900 flex flex-col justify-between">
      {/* Top Header */}
      <header className="bg-forest-800 text-white border-b border-forest-700 shadow-sm sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 py-3.5 flex flex-wrap items-center justify-between gap-3">
          <div
            className="cursor-pointer flex items-center gap-3"
            onClick={() => setActiveTab('home')}
          >
            <div className="w-9 h-9 rounded-xl bg-forest-600 border border-forest-500/50 flex items-center justify-center text-lg shadow-sm">
              🍲
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-extrabold tracking-tight text-white">FoodSense</span>
                <span className="text-[11px] font-medium text-emerald-300 bg-forest-900/60 px-2 py-0.5 rounded-full border border-forest-600/60">
                  Ages 5–20
                </span>
              </div>
              <p className="text-[11px] text-forest-200">
                ICMR-NIN 2020 RDA &amp; IFCT 2017 Verified Indian Nutrition
              </p>
            </div>
          </div>

          <nav className="flex items-center gap-1 bg-forest-900/80 rounded-xl p-1 border border-forest-700/60">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setActiveTab(tab.key)}
                aria-current={activeTab === tab.key ? 'page' : undefined}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                  activeTab === tab.key
                    ? 'bg-terracotta-500 text-white shadow-sm'
                    : 'text-forest-200 hover:text-white hover:bg-forest-700/50'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-4 py-8 flex-1 w-full">
        {activeTab === 'home' && <PlannerPage initialView="home" />}
        {activeTab === 'planner' && <PlannerPage initialView="input" />}
        {activeTab === 'pipeline' && <PipelinePage />}
      </main>

      {/* Footer */}
      <footer className="border-t border-stone-200/80 bg-white/60 py-6 text-xs text-slate-500">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left">
          <div>
            <p className="font-semibold text-slate-700">FoodSense — Eat smart. Feel good.</p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Educational &amp; personalized dietary guidance grounded in ICMR-NIN guidelines.
              Non-medical advice.
            </p>
          </div>
          <div className="text-[11px] text-slate-400">
            <span>Runs offline in-memory</span> · <span>No user data stored</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
