# Optional lab reports

The meal planner works without any clinical input. Supplying one is optional, and
when it is supplied it only ever *adds* dietary emphasis to a plan that was
already going to be built — it never gates the plan, and it can never turn the
tool into a diagnostic.

## What is accepted

Twelve markers, matched by name and unit from free text:

| Marker | Unit | Conventional reference band |
| --- | --- | --- |
| Haemoglobin | g/dL | 12 – 17 |
| Ferritin | ng/mL | 15 – 150 |
| Fasting glucose | mg/dL | 70 – 99 |
| HbA1c | % | no ceiling; ≤ 5.6 typical |
| Total cholesterol | mg/dL | ≤ 200 |
| LDL cholesterol | mg/dL | ≤ 100 |
| HDL cholesterol | mg/dL | ≥ 40 |
| Triglycerides | mg/dL | ≤ 150 |
| Vitamin D (25-OH) | ng/mL | 30 – 100 |
| Vitamin B12 | pg/mL | 200 – 900 |
| Calcium | mg/dL | 8.5 – 10.5 |
| TSH | mIU/L | 0.4 – 4.0 |

Input can be typed, pasted, or uploaded as digital `.pdf`, `.txt`, `.csv`, `.json` or `.md`.
Values may be written as `Hemoglobin: 10.4 g/dL`, `Hb 10.4`, `Fasting glucose
112 mg/dL`, or as CSV/JSON key–value pairs; the parser normalises units where a
conventional alternative is in use (for example `g/L` → `g/dL`).

## Digital PDF Support & Verification Table

- **Digital PDFs**: Extracted using the fast, local `pypdf` engine directly in memory.
- **Verification Table**: Before any extracted lab values are committed to the meal plan,
  users are presented with an interactive verification table where values, units, and
  markers can be reviewed, edited, or toggled on/off.
- **Scanned Image PDFs & Photos**: Image-only scans without a digital text layer cannot be
  reliably OCR'd without potential character misinterpretations. For scanned reports, users
  can verify or manually type their values into the verification table.

## What happens to the data

- The text is parsed **in the request handler, in memory**. Nothing is written to
  disk, nothing is logged, and there is no database.
- The response is sent with `Cache-Control: no-store, private` so neither the
  browser nor an intermediary keeps a copy.
- The plan endpoint is stateless for the same reason: a plan that embeds lab
  findings is returned and then forgotten.
- No value from a lab report is ever sent to any external service. There are no
  outbound network calls in this path at all.

## What the user gets back

Each marker returns its value, unit, reference band and a status of `low`,
`normal` or `high`. A status that has dietary consequences produces a *finding*:
a short message plus a set of dietary focuses the planner understands.

| Finding | Dietary focus | What the planner does |
| --- | --- | --- |
| Low haemoglobin or ferritin | `iron_focus`, `vitamin_c` | ranks iron-rich foods first and favours vitamin-C pairings for absorption |
| High fasting glucose or HbA1c | `glycemic_control` | prefers high-fibre and millet foods, avoids added-sugar sources |
| High total cholesterol, LDL or triglycerides | `low_saturated_fat`, `high_fibre` | avoids ghee-heavy preparations, raises fibre |
| Low HDL | `healthy_fats` | avoids ghee-heavy preparations |
| Low vitamin D | `vitamin_d_focus` | prefers calcium-rich dairy (the dietary half of the answer; sunlight matters more) |
| Low B12 | `vitamin_b12_focus` | prefers dairy and high-protein animal foods |
| Low calcium | `calcium_focus` | prefers dairy and calcium-rich greens |

Serum calcium and TSH are interpreted for the user's information but carry no
food tagging, because no food composition table supports a dietary lever for
them.

Every response ends with the same disclaimer: these are screening interpretations
for dietary planning, not a diagnosis, and abnormal values belong with a
clinician. The wording is a constant, not generated text, so it cannot drift.

## Why this shape

A lab report is health data. The design rule followed throughout is *minimum
retention*: parse what is needed for this one response, then hold nothing. That is
also why the feature is a separate endpoint (`POST /api/lab-report`) from the plan
builder — a user can look at their markers without generating a plan, and a user
can generate a plan without ever sending a marker.
