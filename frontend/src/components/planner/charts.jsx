// Real, dynamically-generated charts for the FoodSense results dashboard.
// Every series here is computed from the MealPlan the API returned.
// Recharts renders them as SVG, responsive and print-ready.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Pie,
  PieChart,
  Radar,
  RadarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

export const MACRO_COLORS = {
  protein: '#2D6A4F', // Forest green
  carbohydrate: '#D97706', // Warm amber
  fat: '#C85A32', // Terracotta
  fibre: '#059669', // Leaf emerald
}

const tooltipStyle = {
  fontSize: 12,
  borderRadius: 8,
  border: '1px solid #e2e8f0',
  backgroundColor: '#ffffff',
  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
}

/** Day-level macronutrient split as a donut (% of energy). Fibre is NOT in energy split. */
export function MacroDonut({ shares }) {
  const data = [
    { name: 'Protein', key: 'protein', value: +(shares.protein * 100).toFixed(1) },
    { name: 'Carbohydrate', key: 'carbohydrate', value: +(shares.carbohydrate * 100).toFixed(1) },
    { name: 'Fat', key: 'fat', value: +(shares.fat * 100).toFixed(1) },
  ]
  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius={55}
          outerRadius={85}
          paddingAngle={3}
          label={(d) => `${d.value}%`}
        >
          {data.map((d) => (
            <Cell key={d.key} fill={MACRO_COLORS[d.key]} />
          ))}
        </Pie>
        <Tooltip formatter={(v) => [`${v}% of energy`, 'Share']} contentStyle={tooltipStyle} />
        <Legend iconType="circle" wrapperStyle={{ fontSize: 12, paddingTop: 6 }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

/** Energy delivered by each meal, against its target share of the day. */
export function EnergyByMeal({ meals, energyTarget }) {
  const share = { breakfast: 0.25, lunch: 0.3, dinner: 0.3, snacks: 0.15 }
  const data = meals.map((m) => ({
    name: m.title,
    Planned: Math.round(m.energy_kcal),
    Target: Math.round((energyTarget || 0) * (share[m.slot] || 0.25)),
  }))
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#475569' }} />
        <YAxis unit=" kcal" tick={{ fontSize: 11, fill: '#64748b' }} width={60} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 6 }} />
        <Bar dataKey="Target" name="Target (RDA split)" fill="#E2E8F0" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Planned" name="Planned Energy" fill="#2D6A4F" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Protein / carbohydrate / fat / fibre grams contributed by each of the 4 meals. */
export function MealMacroBars({ meals }) {
  const data = meals.map((m) => ({
    name: m.title,
    Protein: +m.nutrients.protein_g.toFixed(1),
    Carbohydrate: +m.nutrients.carbohydrate_g.toFixed(1),
    Fat: +m.nutrients.fat_g.toFixed(1),
    Fibre: +m.nutrients.fiber_g.toFixed(1),
  }))
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#475569' }} />
        <YAxis unit=" g" tick={{ fontSize: 11, fill: '#64748b' }} width={50} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 6 }} />
        <Bar dataKey="Protein" fill={MACRO_COLORS.protein} radius={[3, 3, 0, 0]} />
        <Bar dataKey="Carbohydrate" fill={MACRO_COLORS.carbohydrate} radius={[3, 3, 0, 0]} />
        <Bar dataKey="Fat" fill={MACRO_COLORS.fat} radius={[3, 3, 0, 0]} />
        <Bar dataKey="Fibre" fill={MACRO_COLORS.fibre} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Each nutrient as a percentage of its daily ICMR-NIN target. */
export function NutrientAchievement({ rows }) {
  const data = rows
    .filter((r) => r.target && r.key !== 'energy_kcal')
    .map((r) => ({
      name: r.label,
      pct: Math.min(Math.round(r.pct ?? 0), 200),
      actual: r.actual,
      unit: r.unit,
      target: r.target,
      inBand:
        r.band_low != null && r.band_high != null
          ? r.actual >= r.band_low && r.actual <= r.band_high
          : null,
    }))
  return (
    <ResponsiveContainer width="100%" height={Math.max(250, data.length * 28)}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 60 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
        <XAxis type="number" unit="%" domain={[0, 200]} tick={{ fontSize: 11, fill: '#64748b' }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#334155' }} width={100} />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(v, _n, p) => [
            `${p.payload.actual} ${p.payload.unit} (Target: ${p.payload.target} ${p.payload.unit})`,
            '% of Target',
          ]}
        />
        <ReferenceLine x={100} stroke="#1B4332" strokeDasharray="4 4" strokeWidth={1.5} />
        <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
          {data.map((d) => (
            <Cell
              key={d.name}
              fill={
                d.inBand != null
                  ? d.inBand
                    ? '#2D6A4F'
                    : '#D97706'
                  : d.pct >= 100
                  ? '#2D6A4F'
                  : d.pct >= 70
                  ? '#D97706'
                  : '#C85A32'
              }
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** A radar view of the day's key micronutrient coverage, capped at 150%. */
export function NutrientRadar({ rows }) {
  const keys = [
    'calcium_mg',
    'iron_mg',
    'zinc_mg',
    'magnesium_mg',
    'vitamin_c_mg',
    'vitamin_a_rae_ug',
    'folate_dfe_ug',
    'fiber_g',
  ]
  const data = rows
    .filter((r) => keys.includes(r.key) && r.target)
    .map((r) => ({ nutrient: r.label, pct: Math.min(Math.round(r.pct ?? 0), 150) }))
  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="#e2e8f0" />
        <PolarAngleAxis dataKey="nutrient" tick={{ fontSize: 10, fill: '#334155' }} />
        <PolarRadiusAxis angle={90} domain={[0, 150]} tick={{ fontSize: 9, fill: '#64748b' }} unit="%" />
        <Radar
          name="% of target"
          dataKey="pct"
          stroke="#2D6A4F"
          fill="#2D6A4F"
          fillOpacity={0.35}
        />
        <Tooltip contentStyle={tooltipStyle} formatter={(v) => [`${v}% of target`, 'Coverage']} />
      </RadarChart>
    </ResponsiveContainer>
  )
}
