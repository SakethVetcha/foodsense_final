import { useEffect, useRef, useState } from 'react'
import { analyseLabReport, getBodyMetrics } from '../../api'
import LabFindings from './LabFindings'

const DIETS = [
  { value: 'vegetarian', label: 'Vegetarian', desc: 'Plant foods, dairy, grains, pulses' },
  { value: 'eggetarian', label: 'Eggetarian', desc: 'Vegetarian + eggs' },
  { value: 'non_vegetarian', label: 'Non-vegetarian', desc: 'Includes chicken, fish, eggs' },
]

const REGIONS = [
  { value: '', label: 'All-India (Pan-Indian variety)' },
  { value: 'north_indian', label: 'North Indian (Rotis, rajma, paneer, dals)' },
  { value: 'south_indian', label: 'South Indian (Idli, dosa, sambar, rice)' },
  { value: 'east_indian', label: 'East Indian (Khichdi, fish, luchi, dals)' },
  { value: 'west_indian', label: 'West Indian (Poha, thepla, bhakri, dals)' },
]

const GOALS = [
  { value: 'balanced', label: 'Balanced Nutrition', desc: 'Optimal macro & micronutrient density' },
  { value: 'glycemic_control', label: 'Glycemic Control', desc: 'Low GI carbohydrates & steady energy' },
  { value: 'weight_management', label: 'Healthy Weight Support', desc: 'Nutrient-rich, calorie-appropriate' },
]

const ACTIVITIES = [
  { value: 'sedentary', label: 'Sedentary', desc: 'School study, minimal sports' },
  { value: 'moderate', label: 'Moderate', desc: 'Active school play / regular walking' },
  { value: 'heavy', label: 'Heavy / Athletic', desc: 'Daily sports training / intense athletics' },
]

const ALLERGIES_EXCLUSIONS = [
  { value: 'dairy', label: 'Dairy / Lactose-free', tag: 'dairy' },
  { value: 'gluten', label: 'Gluten-free', tag: 'gluten' },
  { value: 'nuts', label: 'Peanuts & Tree Nuts', tag: 'nuts' },
  { value: 'egg', label: 'Egg-free', tag: 'egg' },
  { value: 'soy', label: 'Soy-free', tag: 'soy' },
  { value: 'high_sodium', label: 'Low Sodium', tag: 'high_sodium' },
  { value: 'added_sugar_source', label: 'No Added Sugar', tag: 'added_sugar_source' },
]

export default function PlannerForm({
  profile,
  onChange,
  onGenerate,
  onBackToHome,
  busy,
  lifeStages,
}) {
  const [labText, setLabText] = useState(profile.lab_text || '')
  const [labReport, setLabReport] = useState(null)
  const [labBusy, setLabBusy] = useState(false)
  const [labError, setLabError] = useState(null)
  const [labVerified, setLabVerified] = useState(false)
  const [editableMarkers, setEditableMarkers] = useState([])
  const [fileName, setFileName] = useState('')
  const [bodyMetrics, setBodyMetrics] = useState(null)
  const fileRef = useRef(null)

  const set = (patch) => onChange({ ...profile, ...patch })

  const stage = lifeStages.find(
    (s) => profile.age_years >= s.min_age && profile.age_years <= s.max_age,
  )

  // Live Body Metrics (BMI and BMR)
  useEffect(() => {
    if (profile.age_years && profile.height_cm && profile.weight_kg) {
      getBodyMetrics({
        age_years: profile.age_years,
        sex: profile.sex,
        height_cm: Number(profile.height_cm),
        weight_kg: Number(profile.weight_kg),
      })
        .then(setBodyMetrics)
        .catch(() => setBodyMetrics(null))
    } else {
      setBodyMetrics(null)
    }
  }, [profile.age_years, profile.sex, profile.height_cm, profile.weight_kg])

  const toggleAllergy = (val) => {
    const list = profile.allergies || []
    const updated = list.includes(val) ? list.filter((v) => v !== val) : [...list, val]
    // Also sync to exclude_tags for planner backend compatibility
    const excludeList = profile.exclude_tags || []
    const updatedExcludes = updated.includes(val)
      ? Array.from(new Set([...excludeList, val]))
      : excludeList.filter((v) => v !== val)
    set({ allergies: updated, exclude_tags: updatedExcludes })
  }

  // Handle Lab Report analysis (text or PDF)
  async function analyse(overrideText, overrideBase64) {
    setLabBusy(true)
    setLabError(null)
    try {
      const payload = {
        text: overrideText !== undefined ? overrideText : labText,
        pdf_base64: overrideBase64 || null,
        sex: profile.sex,
      }
      const report = await analyseLabReport(payload)
      setLabReport(report)
      setEditableMarkers(report.markers.map((m) => ({ ...m, include: true })))
      setLabVerified(false)
      set({ lab_text: payload.text || report.markers.map((m) => `${m.label}: ${m.value} ${m.unit}`).join('\n') })
    } catch (e) {
      setLabError(e.message || 'Could not parse lab report.')
    } finally {
      setLabBusy(false)
    }
  }

  function onFileSelected(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setFileName(file.name)

    if (file.type === 'application/pdf' || file.name.endsWith('.pdf')) {
      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result
        const base64 = typeof result === 'string' ? result.split(',')[1] : null
        analyse('', base64)
      }
      reader.readAsDataURL(file)
    } else {
      // Text file
      const reader = new FileReader()
      reader.onload = () => {
        const text = String(reader.result || '')
        setLabText(text)
        analyse(text, null)
      }
      reader.readAsText(file)
    }
  }

  function handleMarkerChange(index, field, value) {
    const updated = [...editableMarkers]
    updated[index][field] = value
    setEditableMarkers(updated)
  }

  function confirmVerifiedMarkers() {
    // Reconstruct lab_text from included and verified markers
    const included = editableMarkers.filter((m) => m.include)
    const text = included.map((m) => `${m.label} ${m.value} ${m.unit}`).join('\n')
    set({ lab_text: text })
    setLabVerified(true)
  }

  function clearLab() {
    setLabText('')
    setLabReport(null)
    setEditableMarkers([])
    setLabVerified(false)
    setFileName('')
    set({ lab_text: null })
    if (fileRef.current) fileRef.current.value = ''
  }

  const isAgeValid = profile.age_years >= 5 && profile.age_years <= 20

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Top Header & Back to Home Button */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={onBackToHome}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-forest-700 hover:text-forest-800 bg-white border border-stone-200 px-3 py-1.5 rounded-lg shadow-sm transition"
        >
          <span>←</span>
          <span>Back to Home</span>
        </button>
        <span className="text-xs text-slate-500">Step 1 of 2: Nutritional Profile</span>
      </div>

      {/* Main Profile Form */}
      <section className="bg-white border border-stone-200/90 rounded-2xl p-6 shadow-sm space-y-6">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Personal Nutritional Profile</h2>
          <p className="text-xs text-slate-500">
            Tell us about the child or young adult (ages 5–20) so we can calibrate accurate ICMR-NIN
            RDA requirements.
          </p>
        </div>

        {/* Age, Sex, Height, Weight Grid */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Age */}
          <div className="space-y-1">
            <label htmlFor="age_input" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Age (5–20 Years) *
            </label>
            <input
              id="age_input"
              type="number"
              min="5"
              max="20"
              value={profile.age_years}
              onChange={(e) => set({ age_years: Number(e.target.value) })}
              className={`w-full bg-cream-50/50 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${
                !isAgeValid ? 'border-rose-400 focus:ring-rose-400' : 'border-slate-300 focus:ring-forest-500'
              }`}
            />
            {!isAgeValid && (
              <p className="text-[11px] text-rose-600 font-medium">Supported age range is 5 to 20 years.</p>
            )}
            {stage && isAgeValid && (
              <p className="text-[11px] text-forest-700 font-medium">{stage.label}</p>
            )}
          </div>

          {/* Sex */}
          <div className="space-y-1">
            <span className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Biological Sex *
            </span>
            <div className="flex gap-2">
              {[
                { key: 'male', label: 'Male' },
                { key: 'female', label: 'Female' },
              ].map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => set({ sex: s.key })}
                  className={`flex-1 rounded-lg py-2 text-xs font-bold transition border ${
                    profile.sex === s.key
                      ? 'bg-forest-700 text-white border-forest-700 shadow-sm'
                      : 'bg-cream-50/50 text-slate-700 border-slate-300 hover:border-forest-500'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-slate-500 leading-tight">
              {profile.sex === 'female' && profile.age_years >= 10
                ? 'Accounts for higher iron RDA (up to 30 mg) for adolescent girls.'
                : 'Calibrates energy & micronutrient baselines.'}
            </p>
          </div>

          {/* Height */}
          <div className="space-y-1">
            <label htmlFor="height_input" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Height (cm, optional)
            </label>
            <input
              id="height_input"
              type="number"
              min="80"
              max="220"
              placeholder="e.g. 155"
              value={profile.height_cm ?? ''}
              onChange={(e) =>
                set({ height_cm: e.target.value === '' ? null : Number(e.target.value) })
              }
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            />
          </div>

          {/* Weight */}
          <div className="space-y-1">
            <label htmlFor="weight_input" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Weight (kg, optional)
            </label>
            <input
              id="weight_input"
              type="number"
              min="10"
              max="150"
              placeholder="e.g. 48"
              value={profile.weight_kg ?? ''}
              onChange={(e) =>
                set({ weight_kg: e.target.value === '' ? null : Number(e.target.value) })
              }
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            />
          </div>
        </div>

        {/* Live Body Metrics Feedback Bar if Height & Weight are provided */}
        {bodyMetrics && (
          <div className="bg-forest-50/70 border border-forest-200 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-3">
              <span className="font-bold text-forest-800">Body Metrics:</span>
              <span className="text-slate-700">
                BMI: <strong className="text-slate-900">{bodyMetrics.bmi}</strong> (
                {bodyMetrics.bmi_category})
              </span>
              <span className="text-slate-700">
                Estimated BMR: <strong className="text-slate-900">{Math.round(bodyMetrics.estimated_bmr_kcal)} kcal/day</strong>
              </span>
            </div>
            <span className="text-[11px] text-forest-700">
              Indian Pediatric / Adolescent percentile cutoffs applied
            </span>
          </div>
        )}

        {/* Activity & Diet Row */}
        <div className="grid sm:grid-cols-3 gap-4 pt-2">
          {/* Activity */}
          <div className="space-y-1">
            <label htmlFor="activity_select" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Physical Activity
            </label>
            <select
              id="activity_select"
              value={profile.activity}
              onChange={(e) => set({ activity: e.target.value })}
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            >
              {ACTIVITIES.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label} — {a.desc}
                </option>
              ))}
            </select>
          </div>

          {/* Diet */}
          <div className="space-y-1">
            <label htmlFor="diet_select" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Dietary Preference
            </label>
            <select
              id="diet_select"
              value={profile.diet}
              onChange={(e) => set({ diet: e.target.value })}
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            >
              {DIETS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label} ({d.desc})
                </option>
              ))}
            </select>
          </div>

          {/* Goal */}
          <div className="space-y-1">
            <label htmlFor="goal_select" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Nutritional Focus
            </label>
            <select
              id="goal_select"
              value={profile.goal}
              onChange={(e) => set({ goal: e.target.value })}
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            >
              {GOALS.map((g) => (
                <option key={g.value} value={g.value}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Regional Cuisine Preferences */}
        <div className="space-y-1 pt-2">
          <label htmlFor="region_select" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
            Regional Indian Cuisine Preference
          </label>
          <select
            id="region_select"
            value={profile.regional_preference || ''}
            onChange={(e) => set({ regional_preference: e.target.value || null })}
            className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
          >
            {REGIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </div>

        {/* Allergies and Exclusions */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between">
            <span className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Food Allergies &amp; Dietary Exclusions
            </span>
            <span className="text-[11px] text-slate-400">Strictly filtered out from all meal categories</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {ALLERGIES_EXCLUSIONS.map((item) => {
              const active = (profile.allergies || []).includes(item.value)
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => toggleAllergy(item.value)}
                  className={`text-xs px-3.5 py-1.5 rounded-lg border font-medium transition ${
                    active
                      ? 'bg-terracotta-600 text-white border-terracotta-600 shadow-sm'
                      : 'bg-white text-slate-700 border-slate-300 hover:border-slate-500'
                  }`}
                >
                  {active ? `✕ ${item.label}` : `+ ${item.label}`}
                </button>
              )
            })}
          </div>
        </div>

        {/* Likes and Dislikes */}
        <div className="grid sm:grid-cols-2 gap-4 pt-2">
          <div className="space-y-1">
            <label htmlFor="likes_input" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Favorite Foods / Likes (Optional)
            </label>
            <input
              id="likes_input"
              type="text"
              placeholder="e.g. roti, paneer, poha, dal makhani"
              value={(profile.likes || []).join(', ')}
              onChange={(e) =>
                set({
                  likes: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            />
            <p className="text-[10px] text-slate-400">Foods prioritized when generating recommendations.</p>
          </div>

          <div className="space-y-1">
            <label htmlFor="dislikes_input" className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
              Disliked Foods to Exclude (Optional)
            </label>
            <input
              id="dislikes_input"
              type="text"
              placeholder="e.g. karela, brinjal, egg"
              value={(profile.dislikes || []).join(', ')}
              onChange={(e) =>
                set({
                  dislikes: e.target.value
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-forest-500"
            />
            <p className="text-[10px] text-slate-400">These will be omitted from all meals.</p>
          </div>
        </div>
      </section>

      {/* Optional Laboratory Report Section with Verification Table */}
      <section className="bg-white border border-stone-200/90 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-900 text-sm flex items-center gap-2">
              <span>Optional Laboratory Report Upload</span>
              <span className="text-[11px] font-normal text-forest-700 bg-forest-50 border border-forest-200 px-2 py-0.5 rounded-full">
                Optional
              </span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Upload a recent digital lab report (.pdf, .txt, .csv, .json) or paste values below to
              refine micronutrient suggestions (e.g., iron, calcium, vitamin D, lipid panel).
            </p>
          </div>
          {(labReport || labText) && (
            <button
              type="button"
              onClick={clearLab}
              className="text-xs text-rose-600 hover:text-rose-800 font-medium"
            >
              Remove Lab Report
            </button>
          )}
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="block text-xs font-medium text-slate-600">
              Upload File (Digital PDF, TXT, CSV, JSON):
            </label>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.csv,.json,.md"
              onChange={onFileSelected}
              className="block w-full text-xs text-slate-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-forest-50 file:text-forest-700 hover:file:bg-forest-100 cursor-pointer"
            />
            {fileName && <p className="text-[11px] text-slate-600">Selected file: <strong>{fileName}</strong></p>}
          </div>

          <div className="space-y-2">
            <label htmlFor="lab_paste_text" className="block text-xs font-medium text-slate-600">Or Paste Lab Results Directly:</label>
            <textarea
              id="lab_paste_text"
              rows={3}
              value={labText}
              onChange={(e) => setLabText(e.target.value)}
              placeholder="Hemoglobin 10.5 g/dL&#10;Vitamin D 18 ng/mL&#10;Fasting Glucose 95 mg/dL"
              className="w-full bg-cream-50/50 border border-slate-300 rounded-lg p-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-forest-500"
            />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => analyse()}
            disabled={labBusy || (!labText.trim() && !fileName)}
            className="bg-forest-600 hover:bg-forest-700 text-white px-4 py-2 rounded-lg text-xs font-semibold disabled:opacity-50 transition"
          >
            {labBusy ? 'Extracting & Parsing…' : 'Analyse & Verify Lab Report'}
          </button>
          {labError && <span className="text-xs text-rose-600 font-medium">{labError}</span>}
        </div>

        {/* Verification Table for Extracted Markers */}
        {editableMarkers.length > 0 && (
          <div className="border border-forest-200 bg-forest-50/30 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-forest-900 uppercase tracking-wide">
                Verify Extracted Lab Values
              </h4>
              <span className="text-[11px] text-forest-700">
                Review and adjust values before confirming
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-forest-200 text-left text-forest-800">
                    <th className="py-1 px-2">Include</th>
                    <th className="py-1 px-2">Marker</th>
                    <th className="py-1 px-2">Value</th>
                    <th className="py-1 px-2">Unit</th>
                    <th className="py-1 px-2">Ref Range</th>
                    <th className="py-1 px-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-forest-100">
                  {editableMarkers.map((m, idx) => (
                    <tr key={m.key} className={m.include ? 'bg-white' : 'bg-slate-100 opacity-60'}>
                      <td className="py-1.5 px-2">
                        <input
                          type="checkbox"
                          checked={m.include}
                          onChange={(e) => handleMarkerChange(idx, 'include', e.target.checked)}
                          className="rounded text-forest-600 focus:ring-forest-500"
                        />
                      </td>
                      <td className="py-1.5 px-2 font-medium text-slate-800">{m.label}</td>
                      <td className="py-1.5 px-2">
                        <input
                          type="number"
                          step="0.1"
                          value={m.value}
                          onChange={(e) => handleMarkerChange(idx, 'value', Number(e.target.value))}
                          className="w-20 border border-slate-300 rounded px-1.5 py-0.5 text-xs font-mono"
                        />
                      </td>
                      <td className="py-1.5 px-2 text-slate-600 font-mono">{m.unit}</td>
                      <td className="py-1.5 px-2 text-slate-500 font-mono">
                        {m.reference_low != null && m.reference_high != null
                          ? `${m.reference_low}–${m.reference_high}`
                          : '—'}
                      </td>
                      <td className="py-1.5 px-2">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                            m.status === 'low'
                              ? 'bg-amber-100 text-amber-800'
                              : m.status === 'high'
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {m.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between pt-2">
              <span className="text-[11px] text-slate-500">
                Non-diagnostic: used strictly to emphasize nutrient density.
              </span>
              <button
                type="button"
                onClick={confirmVerifiedMarkers}
                className="bg-emerald-700 hover:bg-emerald-800 text-white px-3.5 py-1.5 rounded-lg text-xs font-bold transition shadow-sm"
              >
                {labVerified ? '✓ Values Confirmed' : 'Confirm & Apply Verified Values'}
              </button>
            </div>
          </div>
        )}

        {labReport && <LabFindings report={labReport} />}
      </section>

      {/* Submit Button */}
      <div className="flex items-center justify-between pt-2">
        <button
          type="button"
          onClick={onBackToHome}
          className="text-xs font-medium text-slate-500 hover:text-slate-800"
        >
          ← Cancel and return home
        </button>

        <button
          type="button"
          onClick={onGenerate}
          disabled={busy || !isAgeValid}
          className="bg-terracotta-500 hover:bg-terracotta-600 active:bg-terracotta-700 text-white font-bold px-8 py-3.5 rounded-xl text-base shadow-lg transition-all transform hover:-translate-y-0.5 disabled:opacity-50 disabled:pointer-events-none flex items-center gap-2"
        >
          {busy ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              <span>Calculating ICMR-NIN Targets…</span>
            </>
          ) : (
            <>
              <span>Generate 4-Meal Plan</span>
              <span className="text-lg">→</span>
            </>
          )}
        </button>
      </div>
    </div>
  )
}
