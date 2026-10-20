# FoodSense

## Availability-Aware, Verification-Guided Counterfactual Food Recommendation System

FoodSense is a food recommendation system that starts with the meal a user actually plans to eat and the ingredients they actually have available.

Instead of simply recommending a completely different meal, FoodSense finds a small set of modifications that can make the planned meal better aligned with a user's health goal and life-stage safety requirements.

Every generated recommendation is then verified against a curated USDA FoodData Central database before it is presented to the user.

---

## Overview

FoodSense is designed around four stages:

1. **Prediction** — estimates meal suitability using a trained ML surrogate.
2. **Counterfactual Optimization** — searches for small modifications to the user's existing meal using only available foods.
3. **Recommendation Generation** — converts the optimized meal into a readable recommendation.
4. **Verification** — independently checks the final recommendation against USDA food data and safety rules.

The system is designed to work offline after setup and does not require an API key for its default recommendation pipeline.

---

## Key Features

### Availability-Aware Recommendations

FoodSense only searches over foods that are already present in the user's planned meal or pantry.

This prevents the optimizer from recommending unavailable ingredients.

### Modification-Based Recommendations

The system starts from the user's existing meal and searches for the smallest useful set of changes.

Possible modifications include:

- increasing or decreasing quantities
- removing an ingredient
- adding an available pantry ingredient
- changing the preparation form of an ingredient

### Health-Goal Personalization

FoodSense supports multiple health goals:

- Glycemic control
- Weight management
- Balanced nutrition

Goal-specific nutrient requirements are defined through configuration files.

### Age and Life-Stage Personalization

FoodSense supports:

- Toddler
- Adult
- Older adult

Safety rules include preparation-form restrictions and age-specific hazard handling.

For example, a whole grape may be unsafe for a toddler while a suitably quartered grape can be considered a safer form.

### Indian Meal Planner, Ages 5–20

Alongside the pipeline above, the same application ships a second, primary product: an Indian meal planner for ages 5–20 that builds a full day of meals from scratch.

It covers:

- IFCT 2017 Indian food composition, including 30 composite dishes
- six ICMR-NIN 2020 age bands, with sex-specific energy, protein and iron requirements
- four meal categories: breakfast, lunch, dinner and snacks
- optional, non-diagnostic interpretation of laboratory markers

See [Indian Meal Planner](#indian-meal-planner-ages-520) below for the full design.

### Post-Generation Verification

Recommendations are independently verified after generation.

The verifier:

1. matches generated foods against the USDA database
2. recomputes nutrient values
3. compares generated and verified values
4. corrects mismatches where required
5. performs a final safety check

This separates recommendation generation from final verification.

---

# Indian Meal Planner (ages 5–20)

The four-stage pipeline answers *"how can I improve the meal I am about to eat?"*.

The planner answers the other question a parent or a student actually asks: *"what should I eat today?"* — and it answers it with Indian food, Indian requirements, and the person's sex taken seriously.

## Who it is for

Ages 5 to 20, split into the six age bands ICMR-NIN 2020 publishes requirements for. Age is an input, not a label: it selects the requirement table the whole plan is measured against.

| Band | Ages | Energy (boys / girls) | Iron (boys / girls) |
| --- | --- | --- | --- |
| Child | 5–6 | 1360 / 1360 kcal | 11 / 11 mg |
| Child | 7–9 | 1700 / 1700 kcal | 15 / 15 mg |
| Pre-adolescent | 10–12 | 2220 / 2060 kcal | 16 / 28 mg |
| Adolescent | 13–15 | 2860 / 2400 kcal | 22 / 30 mg |
| Late adolescent | 16–18 | 3320 / 2500 kcal | 26 / 32 mg |
| Young adult | 19–20 | 2110 / 1660 kcal | 19 / 29 mg |

## Sex as an input, not a preference

Sex changes the requirement table itself. From 10 years on, girls carry a much higher iron RDA than boys — 28 mg against 16 mg at 10–12, rising to 32 mg against 26 mg at 16–18 — and a different energy requirement at every band.

The planner acts on that difference. An adolescent girl's plans lean iron-rich by default, drawing on dal, leafy greens and jaggery, and report the requirement they are being measured against.

## The four meals

Every plan has four categories, each with its own energy share of the day and its own nutrient targets:

| Meal | Share of the day's energy |
| --- | --- |
| Breakfast | 25% |
| Lunch | 30% |
| Dinner | 30% |
| Snacks | 15% |

Each meal is assembled from **roles** — a cereal staple, a protein dish, a vegetable, a snack — with each role drawing on a pool of real Indian dishes and IFCT ingredients filtered by diet (vegetarian / eggetarian / non-vegetarian) and any excluded tags.

Four details keep the plates realistic:

- **A large slot grows a dish, not a portion.** A 3,800 kcal day for an active 16-year-old boy gets roti *and* rice, rather than one 400 g bowl of khichdi carrying the whole meal.
- **Nothing repeats in a day.** The same sabzi at lunch and dinner is a bug in a demo, so dishes already used today are passed over while a real alternative exists. Across the 324-plan matrix, no day serves the same dish twice.
- **Nuts stay a handful.** A protein-sized portion of nuts is a fat-sized portion of nuts, so nut and oil-seed roles are clamped whatever the protein gap says.
- **A dairy-free day gets a glass of milk.** ICMR-NIN 2020 recommends 300-500 ml of milk or equivalent a day for 5-20 y, and for a vegetarian Indian plate it is the only realistic source of vitamin D and B12. When nothing else on the day is dairy, the snack slot carries 200 ml of milk — never as a hidden ingredient, always as a line on the plate.
- **Cooking oil is on the plate, not hidden.** IFCT measures the food, not the pan it was cooked in. When a day lands below the fat band, the plan adds an explicit "groundnut oil, 5 g" line — capped by the life stage's own visible-fat guidance — and scales the food down by exactly what the oil contributes, so the energy target still holds. A teaspoon is the smallest unit that makes sense, so the oil is handed out a teaspoon at a time while the deficit can pay for it: a day half a point under the band gets one teaspoon, not fifteen grams across three pans. Fat coverage is 100% of plans inside the band either way, because most days reach it from the food itself.

Plans are deterministic under a seed, and every number is a recomputation from the food database — which is what the "verified against IFCT 2017" badge on the dashboard means.

## Measured properties

The planner is exercised across its whole input space — every age band, both sexes, three diets, three activity levels, several seeds — by `experiments/run_planner_matrix.py`, which writes [results/planner_matrix.md](results/planner_matrix.md). On the current build:

| Property | Result |
| --- | --- |
| Days within ±10% of the ICMR-NIN energy target | 324 of 324 |
| Days with protein/carbohydrate/fat inside their energy-share band | 87% / 99% / 100% |
| Days serving the same dish twice | 0 of 324 |
| Days with an empty meal category | 0 of 324 |
| Iron delivered, boys / girls (mean) | 108% / 93% of RDA |
| Plain items per day | 13 |
| Plan build time | 2 ms mean, 63 ms worst |

The protein figure is the honest one: a small share of days land at 11% of energy
from protein against a 12% floor, because an Indian plate built from cereals and
pulses reaches the gram target comfortably but the *share* target only when the
snack and the dal both lean protein-rich. The gap is a gram-level shortfall, not
a safety problem, and it is left visible rather than tuned away.

Those numbers come from a script, not from this file — re-run it rather than trusting the table.

## Nutrient proportions

The dashboard reports energy, protein, carbohydrate, fat, dietary fibre, saturated fat, added sugars, sodium, calcium, iron, zinc, magnesium, potassium, vitamin C, vitamin A, folate and vitamin D — for each meal and for the whole day.

Proportions are reported twice, because the two are different questions:

- **Energy shares** — protein, carbohydrate and fat as a percentage of the day's energy, checked against the ICMR-NIN acceptable ranges.
- **Percentage of target** — grams or milligrams against the requirement for that life stage and sex.

Carbohydrate and fat have no absolute RDA floor, so their targets are the midpoint of their energy-share band converted to grams. That is what makes the proportion requirement displayable rather than asserted.

## Graphs

Five charts, all generated from the returned plan — nothing is hard-coded, and every series is recomputed if the plan changes:

| Chart | Question it answers |
| --- | --- |
| Energy by meal | Did each meal get its share of the day, against its target? |
| Macronutrient split | What is the day's energy actually made of? |
| Macronutrients by meal | How do protein, carbohydrate, fat and fibre distribute across the four meals? |
| Micronutrient coverage | Which micronutrients are covered, and which are thin? |
| Nutrient achievement | Every nutrient as a percentage of its own target, with the 100% line drawn |

## Optional lab reports

A user may paste the numbers from a routine blood report — haemoglobin, ferritin, fasting glucose, HbA1c, a lipid panel, vitamin D, B12, calcium, TSH — and the planner will use them to weight the plan toward the nutrients that matter.

It is optional, non-diagnostic, and inert without input. Nothing is stored, nothing is logged, and the response is marked `no-store`. Scanned PDFs and photographs are **not** read: recovering numbers from a scan means OCR, and a misread value would produce confident wrong dietary advice.

The full design is in [docs/lab_reports.md](docs/lab_reports.md).

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/life-stages` | the six ICMR-NIN 2020 bands with their sex-specific targets |
| `GET /api/indian-foods` | search the Indian database, filtered by meal slot and diet |
| `POST /api/lab-report` | interpret pasted lab values into dietary findings |
| `POST /api/plan` | build a personalised day plan (returns `MealPlan`) |

## Running it

```bash
python -m foodsense.data.build_indian_food_db   # build the Indian database from IFCT 2017
python -m pytest tests/test_planner.py tests/test_indian_data.py tests/test_labs.py
foodsense serve                                  # http://127.0.0.1:8000
```

Open the app and choose **Meal planner** in the header. The original four-stage pipeline is still there under **Research pipeline**.

## Data

- **IFCT 2017** — *Indian Food Composition Tables*, Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K (2017), National Institute of Nutrition, ICMR. 572 foods resolved into the planner's database.
- **Composite dishes** — 30 dishes people actually eat (idli, poha, khichdi, rajma, palak paneer, sambar…), each defined as a small list of IFCT ingredients pinned by food code. Their composition is *computed* from IFCT, never invented, in `src/foodsense/data/indian_dishes.py`.
- **ICMR-NIN 2020** — *Nutrient Requirements for Indians*, ICMR-National Institute of Nutrition. Read as the requirement tables in `configs/life_stages/*.yaml`.

The IFCT extract is not used raw. Energy arrives in kilojoules, minerals in grams, and two vitamins need correcting before they can be compared with an ICMR-NIN requirement: vitamin A is reported as a 1:1 retinol-plus-carotene sum rather than RAE, and the vitamin D column is ergocalciferol whose values for a handful of dried plant foods are two orders of magnitude out. [docs/data_notes.md](docs/data_notes.md) shows the evidence, the conversion, and what is still unfixable (no B12 in IFCT at all).

## What it is not

- Not a medical device. Guidance is dietary, and abnormal lab values belong with a clinician.
- Not a substitute for a dietitian, who knows the person's allergies, culture and cooking.
- Not regionally exhaustive: the dish catalogue is a curated demonstration set, not every Indian preparation.
- Sodium and added-sugar figures exclude salt and sugar added during cooking, because IFCT 2017 does not measure them. The dashboard says so on every plan.

---

# System Architecture

```text
                    User Meal + Pantry
                            |
                            v
                 +----------------------+
                 | Stage 1: Prediction  |
                 | ML Suitability Model |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Stage 2: Counterfactual
                 | Optimization         |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Stage 3: Recommendation
                 | Generation           |
                 +----------+-----------+
                            |
                            v
                 +----------------------+
                 | Stage 4: Verification|
                 | USDA + Safety Rules  |
                 +----------+-----------+
                            |
                            v
                  Verified Recommendation
```

---

# The Four Stages

## Stage 1 — Meal Suitability Prediction

The first stage uses a machine-learning surrogate model to estimate how suitable a meal is for a particular profile and health goal.

The model uses nutrient and meal-level features such as:

- Energy
- Protein
- Sodium
- Iron
- Calcium
- Fibre
- Vitamin C
- Sugars
- Macronutrient proportions
- Maximum item mass share
- Age group
- Health goal
- Health-related flags

FoodSense trains both:

- LightGBM
- XGBoost

The LightGBM model is used as the primary surrogate during the optimization pipeline.

The surrogate is used as a smooth optimization objective. Final validity and safety are determined separately by the rule engine and verification stage.

---

## Stage 2 — Counterfactual Optimization

The optimizer searches for a better version of the user's existing meal.

It operates over:

```text
(quantity in grams, preparation form)
```

for foods available in:

```text
planned meal ∪ pantry
```

Unavailable foods are therefore excluded from the search space.

The objective balances:

- meal suitability
- distance from the original meal
- number of edits
- hard safety constraints

The result is a counterfactual meal: a minimally modified version of the original meal that better satisfies the selected requirements.

The optimizer uses differential evolution for the main FoodSense method.

---

## Stage 3 — Recommendation Generation

The optimized food vector is converted into a human-readable recommendation.

FoodSense includes a deterministic offline `TemplateProvider`, so the normal pipeline does not require an external LLM or API key.

The recommendation explains:

- what should be added
- what should be removed
- what quantities should change
- what preparation form should be used
- why the modification was made

An optional LLM provider can be used for enhanced language generation, but it is not required for the offline demo.

---

## Stage 4 — Verification

The final recommendation is independently verified.

For each generated food, FoodSense:

1. matches it against the USDA database
2. recomputes nutrient values from the matched food
3. checks the generated values against the verified values
4. corrects mismatches beyond the configured tolerance
5. rechecks age and safety constraints

This provides a final verification layer between generated recommendations and the user.

---

# Dataset and Data Processing

FoodSense uses a curated food database built from USDA FoodData Central sources.

The processed database contains:

- **2,590 foods**
- **20 food categories**
- nutrient vectors used throughout the pipeline

The project also uses samples from:

- Food.com
- Nutrition5k

These datasets are used for meal reconstruction, model training, and evaluation.

The repository contains small committed samples so that the project can be run without downloading the complete external corpora.

Full raw datasets are not committed to the repository.

---

# Machine Learning

## Training Dataset

The current training pipeline creates:

- **24,000 training instances**
- **8,000 meals**
- **41 features**
- **19,200 training instances**
- **4,800 held-out instances**

Two models are trained:

### LightGBM

Food.com held-out performance:

```text
RMSE: 0.0576
R²:   0.8632
```

Nutrition5k evaluation:

```text
RMSE: 0.0577
R²:   0.8334
```

Grouped 5-fold cross-validation:

```text
RMSE: 0.0594 ± 0.0009
```

### XGBoost

Food.com held-out performance:

```text
RMSE: 0.0583
R²:   0.8598
```

Nutrition5k evaluation:

```text
RMSE: 0.0579
R²:   0.8321
```

The model training pipeline saves the trained model artifacts and evaluation metrics for later use by the application.

---

# Demo Scenarios

FoodSense includes three predefined scenarios.

## 1. Toddler Choking Safety

### Initial Meal

The meal contains whole grapes and whole peanuts, which present age-specific choking hazards.

### FoodSense Modification

The system:

- changes grapes to a safer quartered form
- removes whole peanuts
- adds ground chicken from the available pantry
- adjusts rice quantity

### Verified Result

```text
261 kcal
17 g protein
50 mg sodium
4.2 g fibre
1.6 mg iron
```

Stage 4 verification:

```text
3/3 foods matched
0 corrections
0 safety fixes
PASS
```

---

## 2. Older Adult Sodium Management

### Initial Meal

The meal contains canned soup and salted crackers.

Initial sodium:

```text
1413 mg
```

The configured per-meal sodium ceiling is:

```text
500 mg
```

### FoodSense Modification

The system removes the high-sodium items and uses available foods to construct a safer alternative.

### Verified Result

```text
323 kcal
21 g protein
492 mg sodium
5.9 g fibre
2.4 mg iron
```

Stage 4 verification:

```text
2/2 foods matched
0 corrections
0 safety fixes
PASS
```

The optimizer did not reach the internal 0.70 suitability target, so the system returned the best safe edit it found rather than claiming that the target had been achieved.

---

## 3. Adult Weight Management

### Initial Meal

The meal contains a burger, fries and cola.

Initial energy:

```text
621 kcal
```

### FoodSense Modification

The system:

- reduces the fries
- reduces the cola
- adds broccoli

### Verified Result

```text
477 kcal
25 g protein
525 mg sodium
8.2 g fibre
5.2 mg iron
```

Stage 4 verification:

```text
4/4 foods matched
0 corrections
0 safety fixes
PASS
```

The optimizer returned its best safe solution because the final rule score remained slightly below the 0.70 target.

---

# Current Demo Verification

The complete offline pipeline has been executed successfully.

The three scenarios completed with:

```text
All 3 scenarios completed and passed Stage-4 verification.
```

The tested pipeline therefore includes:

```text
Data generation
      ↓
Model training
      ↓
Counterfactual optimization
      ↓
Recommendation generation
      ↓
USDA verification
      ↓
Web application
```

---

# Project Structure

```text
FoodSense/
│
├── src/
│   └── foodsense/
│       ├── schemas.py
│       ├── data/
│       ├── constraints/
│       ├── stage1_prediction/
│       ├── stage2_optimizer/
│       ├── stage3_rag/
│       ├── stage4_verification/
│       ├── api/
│       ├── pipeline.py
│       └── cli.py
│
├── frontend/
│   └── React + Vite + Tailwind UI
│
├── configs/
│   ├── goals/
│   ├── age_groups/
│   └── pipeline.yaml
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── samples/
│
├── experiments/
├── results/
├── tests/
├── docs/
│
├── make.ps1
├── Makefile
├── requirements.txt
└── README.md
```

---

# Installation

## Requirements

For the backend:

```text
Python 3.11+
```

For the web interface:

```text
Node.js 18+
```

The project is designed to run locally and does not require an API key for the default offline pipeline.

---

# Running on Windows

The project includes `make.ps1` because GNU Make is not installed on Windows by default.

Open PowerShell in the root of the FoodSense repository.

## 1. Setup

```powershell
.\make.ps1 setup
```

Creates the Python virtual environment and installs the required dependencies.

## 2. Build the Food Database

```powershell
.\make.ps1 data
```

Downloads the required source data and builds the processed USDA food database and supporting samples.

## 3. Train the Model

```powershell
.\make.ps1 train
```

Builds the training set and trains the Stage-1 suitability models.

## 4. Run the Command-Line Demo

```powershell
.\make.ps1 demo
```

Runs all three predefined scenarios end-to-end.

## 5. Start the Web Application

```powershell
.\make.ps1 serve
```

Builds the frontend and starts the FoodSense API and web interface.

Open:

```text
http://127.0.0.1:8000
```

---

# Quick Start After Initial Setup

Once the environment, database and trained models already exist, you do not need to repeat the entire setup process every time.

To start the web application:

```powershell
.\make.ps1 serve
```

Then open:

```text
http://127.0.0.1:8000
```

Keep the terminal running while using the application.

---

# Command-Line Usage

FoodSense also provides a command-line interface.

Example:

```text
foodsense recommend --scenario toddler_choking
```

Run all demo scenarios:

```text
foodsense demo
```

Start the server directly:

```text
python -m foodsense.cli serve
```

Start the server without automatically opening the browser:

```text
python -m foodsense.cli serve --no-open
```

Specify a port:

```text
python -m foodsense.cli serve --no-open --port 8080
```

---

# Reproducibility

The project uses a fixed random seed:

```text
SEED = 42
```

The seed is used throughout the data sampling, training and optimization pipeline.

Results can be regenerated using the experiment scripts provided in the repository.

To regenerate the evaluation:

```text
make eval
```

To verify generated results:

```text
make verify-results
```

For a clean-clone verification, the repository can be set up with a new virtual environment and the complete test/demo pipeline can be executed.

---

# Testing

The project includes an automated test suite covering the major components of the pipeline.

The test suite checks functionality including:

- schemas
- data processing
- rule validation
- optimization
- recommendation generation
- verification
- API behavior
- CLI behavior
- end-to-end scenarios

The project has been successfully executed locally through all three demo scenarios and Stage 4 verification.

---

# Important Design Decisions

## Rules and ML Have Different Responsibilities

The rule engine is responsible for hard safety and compliance decisions.

The ML surrogate provides a smoother objective that the optimizer can search against.

This prevents the optimizer from treating its own learned model as the final authority.

The final decision is made using the rule engine and verification stage.

---

## Availability Is Enforced Structurally

FoodSense does not merely penalize unavailable foods.

Unavailable foods are excluded from the optimization search space.

This means the optimizer cannot select a food that is not in the planned meal or pantry.

---

## Safety Depends on Food Form

Safety is not always a property of an ingredient alone.

For example:

```text
Ingredient: Grapes

Unsafe form:
Whole

Safer form:
Quartered
```

FoodSense therefore represents a meal item using:

```text
(food_id, quantity_g, form)
```

This allows the optimizer to solve certain safety issues by changing the preparation form instead of completely removing the food.

---

# Evaluation Summary

FoodSense was evaluated against several counterfactual approaches over 300 sampled cases.

The evaluation compared:

- FoodSense-DE
- Wachter
- Wachter-style
- DiCE-random
- DiCE-genetic
- Greedy

For the FoodSense-DE method, the reported evaluation included:

```text
Validity:                  29%
Usable validity:           29%
Availability violations:   0%
Safety violations:         0%
Norm-L1:                   0.796
Edits per case:            3.03
```

A key property of the method is that it maintained:

```text
0% availability violations
0% safety violations
```

while actively modifying meals.

The evaluation also documents cases where the optimizer could not reach the target and deliberately reports those cases rather than excluding them.

---

# Known Limitations

FoodSense is a research/capstone prototype and has several limitations.

### Optimization Validity

The main FoodSense method does not achieve perfect validity across all evaluation cases.

Some meals remain below the target because the optimizer returns the best safe solution it can find.

### Demo Scenarios

Two of the three predefined scenarios do not reach the 0.70 target:

- `elderly_sodium`
- `adult_weight`

These cases are intentionally retained rather than hidden from the demo.

### LLM Providers

The default template provider is the path exercised by the offline demo.

External LLM providers are implemented but were not runtime-verified in the development environment because no live API key was available.

### Docker

Docker configuration is included in the project but is not part of the tested demo path.

The recommended demonstration path is the local `make.ps1 serve` workflow.

### Not a Clinical Tool

FoodSense is an academic research prototype.

Its recommendations should not be treated as medical or clinical advice.

---

# Technology Stack

## Backend

- Python
- FastAPI
- Pydantic
- LightGBM
- XGBoost
- scikit-learn
- SciPy
- SQLite
- PyArrow / Parquet

## Frontend

- React
- Vite
- Tailwind CSS
- Node.js

## Data

- USDA FoodData Central
- Food.com sample data
- Nutrition5k sample data
- IFCT 2017 Indian Food Composition Tables (for the ages 5–20 planner)
- ICMR-NIN 2020 Nutrient Requirements for Indians (for the ages 5–20 planner)

## Optimization

- Differential Evolution
- Counterfactual optimization
- Constraint-based safety handling

---

# Research Foundation

FoodSense extends the architecture of:

**MetaPlate — Arefeen, Johnston & Ghasemzadeh, IEEE Journal of Biomedical and Health Informatics, 2026.**

The project extends the underlying counterfactual recommendation approach through:

1. Availability-aware optimization
2. Modification-based meal editing
3. Post-generation verification
4. Generalized health goals
5. Age/life-stage personalization

---

# Data Sources

### USDA FoodData Central

Used as the primary source for the curated food and nutrient database.

### Food.com

Used for recipe and meal examples.

### Nutrition5k

Used as an additional evaluation corpus.

The project keeps small seeded samples in the repository so that the pipeline can be reproduced without requiring the full external datasets.

### IFCT 2017

*Indian Food Composition Tables*, National Institute of Nutrition, ICMR.

Used as the food-composition source for the Indian meal planner. The full table is bundled, and the composite dishes are computed from its ingredient rows.

### ICMR-NIN 2020

*Nutrient Requirements for Indians*, ICMR-National Institute of Nutrition.

Used as the requirement source for the meal planner's six age bands, including the sex-specific energy, protein and iron values.

---

# Academic Project Information

**Course:** BCSE497J — PROJECT-I

**Institution:** Vellore Institute of Technology

**Project:** FoodSense

> Project information will be added here.

---

# Acknowledgements

FoodSense builds upon research, datasets and public guidance from:

- MetaPlate / Arefeen, Johnston & Ghasemzadeh
- USDA FoodData Central
- Food.com
- Nutrition5k
- IFCT 2017, National Institute of Nutrition, ICMR
- ICMR-NIN 2020, Nutrient Requirements for Indians
- NASEM Dietary Reference Intakes
- AAP / CDC guidance
- Dietary Guidelines for Americans
- American Heart Association
- ESPEN / ASPEN
- IDDSI

---

# License

The project code is released under the MIT License.

The datasets and external data sources remain subject to their respective upstream terms.

See `LICENSE` for the complete software license.

---

# Project Status

**Status: Demo-ready**

The current implementation successfully runs the complete offline pipeline:

```text
Input meal
    ↓
Meal suitability prediction
    ↓
Counterfactual optimization
    ↓
Natural-language recommendation
    ↓
USDA verification
    ↓
Verified meal
```

The web application is available locally through:

```text
http://127.0.0.1:8000
```

The three included demonstration scenarios have been executed successfully and passed Stage-4 verification.

The ages 5–20 Indian meal planner runs end to end as well: matrix-tested across every age band, both sexes, three diets, three activity levels and multiple seeds, with daily energy landing within 10% of the ICMR-NIN target and no dish repeated across a day.
