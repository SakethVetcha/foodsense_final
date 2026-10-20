# Data notes: what the IFCT 2017 extract does, and where we had to intervene

The Indian food database is built from the machine-readable IFCT 2017 extract
(`data/raw/ifct/ifct_compositions.csv`, 542 foods, fetched from
[ifct2017/compositions](https://github.com/ifct2017/compositions)). Everything
downstream — the planner, the charts, the report tables — reads the database, so
a unit or provenance problem inside the extract becomes a wrong number on screen.

Four of them were real. This file records what we found, how we checked it, and
what the code does about it, so that a reviewer can re-run the checks rather than
trust the summary.

---

## 1. Energy is in kilojoules

`enerc` is kJ. Dividing by 4.184 gives kcal, and the result matches the printed
book (rice, milled, raw: IFCT prints 356 kcal; we load 356.4).

A minority of rows report no energy at all, or an energy that disagrees with
their own macronutrients by more than 25% — every edible oil is in this group.
For those, energy falls back to Atwater factors. The rule lives in
`load_ifct_table` and is tested in `tests/test_indian_data.py`.

## 2. Minerals are stored in grams

`ca`, `fe`, `zn`, `na`, `k`, `mg`, `p`, `cu` are grams per 100 g, so cow milk's
`0.118` is 118 mg of calcium — which is exactly what the book prints. Verified
against published values for milk (118 mg), spinach (82 mg), rice (7.5 mg) and
curry leaves (659 mg). A unit slip here would be a silent 1000x error, so
`test_minerals_are_in_milligrams_not_grams` guards it.

## 3. Vitamin A is not RAE, and we recompute it

IFCT's `vita` column is **retinol plus total carotenoids added 1:1 by weight**.
You can see this directly in the data: for spinach `vita == carot` (2605 ug),
for goat liver `vita == retol` (15655 ug).

A 1:1 sum is a retinol-equivalent convention, not the *retinol activity
equivalent* (RAE) that the ICMR-NIN 2020 RDAs — the targets this planner builds
to — are written in. Comparing the two overstates vitamin A from plant foods by
up to 12x. Before the fix, a normal vegetarian day for a 14-year-old girl read
**886% of the vitamin A RDA**; almost all of it was carotene counted at full
weight.

`load_ifct_table` now derives RAE the way the Institute of Medicine defines it:

```
vitamin_a_rae_ug = retinol + beta-carotene / 12
```

Spot-checks after the change (per 100 g):

| Food | `vita` (1:1) | RAE now | International reference |
|---|---|---|---|
| Spinach | 2605 | 217 | 469 (USDA, raw spinach) |
| Carrot, orange | 8077 | 686 | 835 (USDA, raw carrot) |
| Chicken liver | 3486 | 3486 | 3296 (USDA) |
| Cow milk | 13.7 | 1.1 | 46 (USDA, whole milk) |

Animal sources are unchanged, as they should be — they are retinol. Plant
sources drop by roughly an order of magnitude and land in the range other
composition tables report. Milk is now the visible outlier, and it is low because
IFCT's own carotenoid figure for Indian cow milk (13.7 ug/100 g) is low; we
convert the table's number rather than substitute another table's.

## 4. Vitamin D cannot be trusted outside animal foods and mushrooms

IFCT's `vitd` column is **ergocalciferol**: it equals `ergcal` row for row
(Pearson r = 0.997, ratio exactly 1.0 on every row where both are non-zero), so
it measures plant/fungal D2 rather than total vitamin D.

Where that is fine, it is very fine:

| Food | Vitamin D (ug/100 g) | Plausible? |
|---|---|---|
| Cow milk, whole | 1.22 | yes — 3 ug per glass |
| Rohu | 1.01 | yes |
| Pomfret, black | 2.94 | yes |
| Button mushroom | 20.5 | yes — mushrooms are a real D2 source |

Where it is not fine, it is not fine by two orders of magnitude:

| Food | Vitamin D (ug/100 g) | Consequence |
|---|---|---|
| Pomegranate, maroon seeds | 109 | one 100 g serving = 7x an adolescent's RDA |
| Curry leaves | 117 | 10 g of tempering = 78% of the RDA |
| Pippali | 118 | — |
| Oyster mushroom, dried | 109 | — |
| Gingelly seeds, brown | 76.5 | — |
| Soya bean, white | 69.8 | — |

Before the fix, a vegetarian plan for a 14-year-old girl delivered **199 ug of
vitamin D against a 15 ug RDA — 1327%** — with the whole excess traceable to a
single pomegranate snack and a curry-leaf tempering. That is not a plan a
nutritionist would sign, and a day above the tolerable upper intake level
(100 ug) should never appear as a green tick in a child's dashboard.

`VITAMIN_D_GROUPS` in `src/foodsense/data/indian_food.py` keeps vitamin D for
dairy, egg, poultry, meat, fish, shellfish, mushrooms and fats, and zeroes it
elsewhere. Nothing is invented and no value is rescaled: the questionable
contributions are removed and the remaining ones are the table's own numbers.

The consequence is honest and worth showing rather than hiding: **a plan lands
around a quarter of the vitamin D RDA** (mean 4.1 ug against 15), because Indian
milk is not fortified and mushrooms are not a staple. The dashboard says so, and
the planner's insight text points at sunlight exposure and fortified milk instead
of pretending a pomegranate fixed it. The one dietary lever the planner can pull
is the glass of milk it puts on a dairy-free day (see `add_dairy_serving`), which
is the difference between the 0 ug a paneer-only day used to show and the 2.4 ug
milk actually carries.

---

## What is still wrong, and is documented rather than fixed

* **Vitamin B12 is absent from IFCT 2017.** The database stores 0 for every
  Indian food, and the planner therefore has no B12 floor. A vegetarian Indian
  diet is genuinely at risk here; the app's disclaimer says so.
* **Added sugars and sodium are under-counted.** IFCT measures the food, not the
  cooking: salt and sugar added at the stove are invisible to it. Every plan
  carries this caveat on screen.
* **`vita`/`vitd` provenance.** We know the columns' arithmetic (above). We do
  not know which analytical method produced the raw D2 figures, and it is not
  something we can settle from the CSV alone.
