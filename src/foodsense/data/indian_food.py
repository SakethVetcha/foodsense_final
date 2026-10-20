"""Build the curated Indian food database from IFCT 2017.

This is the Indian-data counterpart of :mod:`foodsense.data.build_food_db`. It
reads the machine-readable IFCT 2017 composition table, composes the composite
dishes in :mod:`foodsense.data.indian_dishes` from IFCT ingredients, and writes a
food database in the *same schema* the rest of the pipeline already speaks --
``data/processed/indian_food_db.{parquet,sqlite}``.

Because the schema is identical, nothing downstream changes: ``FoodDB`` loads it,
``RuleEngine`` scores against it, ``NutrientVector`` sums it and the meal planner
reasons over it. The only thing that differs from the USDA database is where the
numbers came from.

What IFCT gives us, and how it is stored
----------------------------------------
IFCT 2017 publishes per-100 g values with an unconventional but internally
consistent unit scheme, verified against the published tables:

* ``enerc``  -- energy in **kJ**. Divided by 4.184 to get kcal. (A small number
  of rows report no energy or an energy inconsistent with their macronutrients --
  every edible oil, for instance -- so energy falls back to Atwater factors when
  the two disagree by more than 25%.)
* protein / fat / carbohydrate / fibre / moisture -- **grams**.
* minerals (Ca, Fe, Zn, Na, K, Mg, P, Cu, cholesterol) -- **grams**, multiplied by
  1000 to give the mg the pipeline expects.
* vitamins C, E, B1, B2, B3, B6 and selenium / vitamin D / K / folate --
  stored in grams and scaled to their conventional units (mg or ug).

Vitamin A is the one nutrient that is *derived* rather than copied. IFCT's
``vita`` column adds retinol and total carotenoids at a 1:1 weight, which is a
retinol-equivalent convention, not the retinol-activity equivalent (RAE) the
ICMR-NIN 2020 RDAs are written in. Comparing the two directly overstates plant
vitamin A by up to 12x (spinach reads 2605 ug "RAE" instead of 217). We
recompute RAE the way the US Institute of Medicine defines it -- retinol plus
beta-carotene / 12 -- from IFCT's own ``retol`` and ``carot`` columns.

Vitamin D needs no conversion but does need a filter: almost every non-zero value
in the extract is ergocalciferol (``vitd`` equals ``ergcal`` row for row), so it
measures plant/fungal D2. Animal foods carry small, plausible values (cow milk
1.2 ug/100 g, rohu 1.0) and are kept, as are mushrooms. Outside those groups the
column is not a usable per-100 g measure -- it reports 109 ug for pomegranate,
117 for curry leaves and 118 for pippali -- so only :data:`VITAMIN_D_GROUPS`
contribute it. ``docs/data_notes.md`` records the evidence and the decision.

IFCT 2017 does **not** report vitamin B12, so ``vitamin_b12_ug`` is 0 for every
Indian food. That is a property of the source, documented here rather than
papered over; the planner simply does not use a B12 floor.

Composite dishes
----------------
``grup`` = "Composite Dishes" rows are computed, not measured: each dish's
per-100 g composition is the ingredient-summed composition of its IFCT
ingredients over its cooked yield. See :mod:`foodsense.data.indian_dishes`.

Run it with::

    python -m foodsense.data.build_indian_food_db
    python -m foodsense.data.build_indian_food_db --stats

Source
    Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K (2017). Indian Food
    Composition Tables. National Institute of Nutrition, ICMR, Hyderabad.
    https://www.nin.res.in/ebooks/IFCT2017.pdf
    Machine-readable extraction: https://github.com/ifct2017/compositions
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from foodsense import RAW_DIR
from foodsense.data.indian_dishes import DISHES, diet_of_ifct_tags
from foodsense.schemas import NUTRIENTS, Form

__all__ = [
    "IFCT_CSV",
    "IndianBuildReport",
    "IFCT_NUTRIENT_MAP",
    "curate_indian_food_db",
    "load_ifct_table",
]

#: Committed IFCT extract. The download step in ``build_indian_food_db`` refreshes
#: it if absent, so a clean clone still builds offline once fetched.
IFCT_CSV = RAW_DIR / "ifct" / "ifct_compositions.csv"
IFCT_URL = "https://raw.githubusercontent.com/nodef/ifct2017/main/compositions/index.csv"


# ---------------------------------------------------------------------------
# Unit-correct nutrient mapping:  FoodSense nutrient -> (IFCT code, multiplier)
# ---------------------------------------------------------------------------
#: See the module docstring for how these multipliers were verified.
IFCT_NUTRIENT_MAP: dict[str, tuple[str, float]] = {
    "energy_kcal": ("enerc", 1.0 / 4.184),  # kJ -> kcal
    "protein_g": ("protcnt", 1.0),
    "carbohydrate_g": ("choavldf", 1.0),
    "fiber_g": ("fibtg", 1.0),
    "fat_g": ("fatce", 1.0),
    "saturated_fat_g": ("fasat", 1.0),
    "trans_fat_g": ("fatrn", 1.0),
    "monounsaturated_fat_g": ("fams", 1.0),
    "polyunsaturated_fat_g": ("fapu", 1.0),
    "cholesterol_mg": ("cholc", 1000.0),
    "sodium_mg": ("na", 1000.0),
    "potassium_mg": ("k", 1000.0),
    "calcium_mg": ("ca", 1000.0),
    "iron_mg": ("fe", 1000.0),
    "magnesium_mg": ("mg", 1000.0),
    "zinc_mg": ("zn", 1000.0),
    "phosphorus_mg": ("p", 1000.0),
    "copper_mg": ("cu", 1000.0),
    "selenium_ug": ("se", 1e6),
    "vitamin_c_mg": ("vitc", 1000.0),
    "vitamin_d_ug": ("vitd", 1e6),
    "vitamin_e_mg": ("vite", 1000.0),
    "vitamin_k_ug": ("vitk", 1e6),
    "thiamin_mg": ("thia", 1000.0),
    "riboflavin_mg": ("ribf", 1000.0),
    "niacin_mg": ("nia", 1000.0),
    "vitamin_b6_mg": ("vitb6c", 1000.0),
    "folate_dfe_ug": ("folsum", 1e6),
    "water_g": ("water", 1.0),
}

#: Vitamin A is retinol + beta-carotene / 12 (RAE), not IFCT's 1:1 ``vita`` sum.
_RETINOL_CODE = "retol"
_CAROTENE_CODE = "carot"
_CAROTENE_TO_RAE = 12.0

#: Food groups whose vitamin D is kept.
#:
#: The IFCT extract's ``vitd`` column is ergocalciferol (it equals ``ergcal`` row
#: for row), i.e. plant/fungal D2. Animal foods carry small, plausible values
#: (cow milk 1.2 ug/100 g, rohu 1.0, pomfret 2.9) and mushrooms are a real D2
#: source, so those are kept. Outside them the column cannot be a per-100 g
#: measure of the food as eaten: it reports 109 ug for pomegranate, 117 for curry
#: leaves and 118 for pippali -- 7x an adolescent's whole-day RDA in a single
#: serving, and twice the tolerable upper intake level. Propagating that into a
#: child's plan would be worse than dropping it, so dried fruits, spices, seeds
#: and cereals contribute no vitamin D here. ``docs/data_notes.md`` records the
#: anomaly and the numbers behind this decision.
VITAMIN_D_GROUPS: frozenset[str] = frozenset(
    {
        "Milk and Milk Products",
        "Egg and Egg Products",
        "Poultry",
        "Animal Meat",
        "Marine Fish",
        "Fresh Water Fish and Shellfish",
        "Marine Shellfish",
        "Marine Mollusks",
        "Mushrooms",
        "Edible Oils and Fats",
    }
)

#: Free sugars are reported as individual mono-/disaccharides; total sugars is
#: their sum. (IFCT has no single "total sugars" column.)
_SUGAR_CODES = ("frus", "glus", "sucs", "mals", "lactose", "rafs")

# ---------------------------------------------------------------------------
# Taxonomy:  IFCT food group -> FoodSense category
# ---------------------------------------------------------------------------

CATEGORY_MAP: dict[str, str] = {
    "Cereals and Millets": "grain",
    "Grain Legumes": "legume",
    "Milk and Milk Products": "dairy",
    "Fruits": "fruit",
    "Green Leafy Vegetables": "vegetable",
    "Other Vegetables": "vegetable",
    "Roots and Tubers": "root",
    "Nuts and Oil Seeds": "nut_seed",
    "Edible Oils and Fats": "fat_oil",
    "Egg and Egg Products": "egg",
    "Poultry": "poultry",
    "Animal Meat": "meat",
    "Marine Fish": "fish",
    "Fresh Water Fish and Shellfish": "fish",
    "Marine Shellfish": "fish",
    "Marine Mollusks": "fish",
    "Condiments and Spices": "spice",
    "Sugars": "sweets",
    "Miscellaneous Foods": "beverage",
    "Mushrooms": "vegetable",
    "Composite Dishes": "prepared",
}

#: Preparation forms available to each category. Mirrors the USDA builder's map
#: so the optimiser and the rule engine behave identically on both databases.
FORMS_BY_CATEGORY: dict[str, tuple[Form, ...]] = {
    "fruit": (Form.WHOLE, Form.QUARTERED, Form.SLICED, Form.CHOPPED, Form.MASHED, Form.PUREED),
    "vegetable": (Form.WHOLE, Form.CHOPPED, Form.SLICED, Form.SOFT_COOKED, Form.MASHED, Form.PUREED),
    "root": (Form.WHOLE, Form.CHOPPED, Form.SLICED, Form.SOFT_COOKED, Form.MASHED, Form.PUREED),
    "legume": (Form.WHOLE, Form.SOFT_COOKED, Form.MASHED, Form.PUREED),
    "grain": (Form.WHOLE, Form.SOFT_COOKED, Form.MASHED),
    "dairy": (Form.WHOLE, Form.SLICED, Form.MASHED, Form.PUREED),
    "meat": (Form.WHOLE, Form.SLICED, Form.CHOPPED, Form.MINCED, Form.GROUND, Form.SOFT_COOKED),
    "poultry": (Form.WHOLE, Form.SLICED, Form.CHOPPED, Form.MINCED, Form.GROUND, Form.SOFT_COOKED),
    "fish": (Form.WHOLE, Form.CHOPPED, Form.MINCED, Form.MASHED, Form.SOFT_COOKED),
    "egg": (Form.WHOLE, Form.CHOPPED, Form.MASHED, Form.SOFT_COOKED),
    "nut_seed": (Form.WHOLE, Form.CHOPPED, Form.GROUND, Form.THIN_SPREAD),
    "fat_oil": (Form.WHOLE, Form.THIN_SPREAD),
    "sweets": (Form.WHOLE, Form.CHOPPED),
    "spice": (Form.WHOLE, Form.GROUND, Form.MINCED),
    "beverage": (Form.WHOLE,),
    "prepared": (Form.WHOLE, Form.SLICED, Form.CHOPPED, Form.MASHED),
}

#: Meal slots an ingredient group can plausibly appear in. Composite dishes carry
#: their own slots; this is only for raw ingredients.
SLOTS_BY_GROUP: dict[str, tuple[str, ...]] = {
    "Cereals and Millets": ("breakfast", "lunch", "dinner"),
    "Grain Legumes": ("lunch", "dinner"),
    "Milk and Milk Products": ("breakfast", "snacks"),
    "Fruits": ("breakfast", "snacks"),
    "Green Leafy Vegetables": ("lunch", "dinner"),
    "Other Vegetables": ("lunch", "dinner"),
    "Roots and Tubers": ("lunch", "dinner"),
    "Nuts and Oil Seeds": ("snacks",),
    "Edible Oils and Fats": ("lunch", "dinner"),
    "Egg and Egg Products": ("breakfast", "lunch", "dinner"),
    "Poultry": ("lunch", "dinner"),
    "Animal Meat": ("lunch", "dinner"),
    "Marine Fish": ("lunch", "dinner"),
    "Fresh Water Fish and Shellfish": ("lunch", "dinner"),
    "Marine Shellfish": ("lunch", "dinner"),
    "Marine Mollusks": ("lunch", "dinner"),
    "Condiments and Spices": ("lunch", "dinner"),
    "Sugars": ("snacks",),
    "Miscellaneous Foods": ("snacks",),
    "Mushrooms": ("lunch", "dinner"),
    "Composite Dishes": ("breakfast", "lunch", "dinner", "snacks"),
}

_GLUTEN_RE = re.compile(r"\b(wheat|barley|rye|semolina|vermicelli|suji|maida|atta|bulgur)\b", re.I)
_REFINED_RE = re.compile(r"\b(refined|milled|semolina|vermicelli|maida|polished)\b", re.I)
_WHOLE_RE = re.compile(r"\b(whole|brown|atta|parboiled)\b", re.I)
_NUT_HAZARD_RE = re.compile(
    r"\b(almond|cashew|pistachio|walnut|ground\s?nut|peanut|pine seeds|"
    r"sunflower seeds|gingelly|sesame|linseed|mustard seeds|niger seeds|safflower seeds)\b",
    re.I,
)

#: Codes whose names carry no identity beyond a variety number are kept as-is;
#: nothing is dropped. IFCT is already a curated table.


@dataclass
class IndianBuildReport:
    """What the Indian build produced. Named to avoid clashing with the USDA report."""

    n_ifct_rows: int
    n_dishes: int
    n_final: int
    category_counts: dict[str, int]
    slot_counts: dict[str, int]
    diet_counts: dict[str, int]
    nutrient_coverage: dict[str, float] = field(default_factory=dict)
    source: str = "IFCT 2017 (ICMR-NIN) — https://www.nin.res.in/ebooks/IFCT2017.pdf"


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------

_MISSING = {"", "-", "--", "nd", "na", "n/a", "tr", "trace", "*", "**"}


def _num(value: object) -> float:
    """Parse an IFCT cell into a float, treating textual markers as zero."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in _MISSING:
        return 0.0
    try:
        return float(text)
    except ValueError:
        # e.g. "<0.5"; take the numeric part.
        m = re.search(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
        return float(m.group()) if m else 0.0


def _atwater(protein: float, carb: float, fat: float, fibre: float) -> float:
    return 4.0 * protein + 4.0 * carb + 9.0 * fat + 2.0 * fibre


# ---------------------------------------------------------------------------
# IFCT table -> FoodSense nutrient rows
# ---------------------------------------------------------------------------


def load_ifct_table(path: Path | None = None) -> list[dict[str, object]]:
    """Parse the IFCT composition CSV into FoodSense-nutrient dicts.

    Returns one dict per food with ``fdc_id``/``name``/``grup``/``tags`` plus one
    key per :data:`foodsense.schemas.NUTRIENTS` entry, in the pipeline's units.
    """
    src = Path(path or IFCT_CSV)
    if not src.exists():
        raise FileNotFoundError(
            f"IFCT table not found at {src}. Fetch it with "
            f"`python -m foodsense.data.build_indian_food_db --download`."
        )

    out: list[dict[str, object]] = []
    with src.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            nutrients: dict[str, float] = {}
            for nutrient, (source_key, multiplier) in IFCT_NUTRIENT_MAP.items():
                nutrients[nutrient] = _num(row.get(source_key)) * multiplier

            # Vitamin A as RAE: retinol counts as-is, carotene at 1/12.
            nutrients["vitamin_a_rae_ug"] = (
                _num(row.get(_RETINOL_CODE)) + _num(row.get(_CAROTENE_CODE)) / _CAROTENE_TO_RAE
            ) * 1e6

            # Vitamin D: only from groups where it is a real dietary source. See
            # the :data:`VITAMIN_D_GROUPS` note for why the rest is dropped.
            group = str(row.get("grup", "")).strip()
            if group not in VITAMIN_D_GROUPS:
                nutrients["vitamin_d_ug"] = 0.0

            # Total sugars = sum of the reported mono-/disaccharides.
            nutrients["sugars_g"] = sum(_num(row.get(c)) for c in _SUGAR_CODES)
            nutrients["added_sugars_g"] = 0.0
            nutrients["vitamin_b12_ug"] = 0.0  # not reported by IFCT 2017

            # Energy sanity pass: trust IFCT unless it is missing or disagrees
            # with the macronutrients by more than 25% (a small number of rows,
            # notably every edible oil, report no energy at all).
            macro_kcal = _atwater(
                nutrients["protein_g"],
                nutrients["carbohydrate_g"],
                nutrients["fat_g"],
                nutrients["fiber_g"],
            )
            reported = nutrients["energy_kcal"]
            if reported <= 0 or (macro_kcal > 20 and abs(reported - macro_kcal) / macro_kcal > 0.25):
                nutrients["energy_kcal"] = round(macro_kcal, 2)

            out.append(
                {
                    "fdc_id": str(row["code"]).strip(),
                    "name": str(row["name"]).strip(),
                    "grup": str(row.get("grup", "")).strip(),
                    "lang": str(row.get("lang", "")).strip(),
                    "ifct_tags": str(row.get("tags", "")).strip(),
                    **nutrients,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Composite dishes
# ---------------------------------------------------------------------------


def _compose_dishes(ingredients: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compute per-100 g composition for every dish from its IFCT ingredients."""
    by_code = {str(r["fdc_id"]): r for r in ingredients}
    dishes: list[dict[str, object]] = []
    for dish in DISHES:
        total = {n: 0.0 for n in NUTRIENTS}
        for code, grams in dish.ingredients.items():
            record = by_code.get(code)
            if record is None:
                raise KeyError(
                    f"Dish {dish.code} ({dish.name!r}) references IFCT code {code!r}, "
                    f"which is not in the table. Fix the dish or the table version."
                )
            for n in NUTRIENTS:
                total[n] += float(record[n]) * grams / 100.0
        factor = 100.0 / dish.serving_g
        per_100g = {n: round(total[n] * factor, 4) for n in NUTRIENTS}

        # Grain-class tags are inherited from the ingredients: "Chapati (roti)"
        # carries no grain word in its own name, but it is made of wheat flour,
        # so a gluten exclusion must still remove it.
        ingredient_names = " ".join(str(by_code[c]["name"]) for c in dish.ingredients)
        derived: list[str] = []
        if _GLUTEN_RE.search(ingredient_names):
            derived.append("gluten")
        if _REFINED_RE.search(ingredient_names):
            derived.append("refined_grain")
        if _WHOLE_RE.search(ingredient_names):
            derived.append("whole_grain")
        dishes.append(
            {
                "fdc_id": dish.code,
                "name": dish.name,
                "grup": "Composite Dishes",
                "lang": "",
                "ifct_tags": "",
                "diet": dish.diet,
                "slots": dish.slots,
                "dish_tags": tuple(dish.tags) + tuple(derived),
                **per_100g,
            }
        )
    return dishes


# ---------------------------------------------------------------------------
# Annotation: category, forms, hazard, tags
# ---------------------------------------------------------------------------


def _category(grup: str) -> str:
    return CATEGORY_MAP.get(grup, "prepared")


def _forms(category: str) -> tuple[list[str], str]:
    forms = FORMS_BY_CATEGORY.get(category, (Form.WHOLE,))
    return [f.value for f in forms], forms[0].value


def _hazard(name: str, category: str) -> str:
    if category == "nut_seed" and _NUT_HAZARD_RE.search(name) and "oil" not in name.lower():
        return "nut"
    return ""


def _tags(row: dict[str, object], category: str) -> list[str]:
    """Meal-slot, diet and nutrient/name-derived tags.

    Slot tags (``meal_breakfast`` ...) let the planner filter foods by meal
    without a second table, and reuse the existing tag channel rather than
    widening the database schema.
    """
    name = str(row["name"])
    tags: set[str] = set()

    if category == "prepared":
        slots = row.get("slots") or SLOTS_BY_GROUP["Composite Dishes"]
        diet = str(row.get("diet", "vegetarian"))
        for extra in row.get("dish_tags", ()):  # type: ignore[union-attr]
            tags.add(str(extra))
    else:
        slots = SLOTS_BY_GROUP.get(str(row["grup"]), ("lunch", "dinner"))
        diet = diet_of_ifct_tags(set(str(row.get("ifct_tags", "")).split()))

    for slot in slots:
        tags.add(f"meal_{slot}")
    tags.add(f"diet_{diet}")
    # The category is also a tag, because the planner's lab-report preferences
    # ask for "dairy" by name (low vitamin D, low B12). Without this they asked
    # for a tag nothing carried and the preference silently did nothing.
    tags.add(category)

    # Nutrient-threshold tags, mirroring the USDA builder's rules.
    if float(row["sodium_mg"]) >= 300:
        tags.add("high_sodium")
    if float(row["potassium_mg"]) >= 400:
        tags.add("high_potassium")
    if float(row["vitamin_k_ug"]) >= 50:
        tags.add("leafy_green_vitk")
    if float(row["calcium_mg"]) >= 200:
        tags.add("calcium_rich")
    if float(row["iron_mg"]) >= 3.0:
        tags.add("iron_rich")
    if float(row["fiber_g"]) >= 5.0:
        tags.add("high_fibre")
    if float(row["protein_g"]) >= 15.0:
        tags.add("high_protein")

    if category in {"sweets"} or re.search(r"\b(jaggery|sugar|syrup)\b", name, re.I):
        tags.add("added_sugar_source")
    if _GLUTEN_RE.search(name):
        tags.add("gluten")
    if _REFINED_RE.search(name):
        tags.add("refined_grain")
    if _WHOLE_RE.search(name):
        tags.add("whole_grain")
    if re.search(r"\b(toddy|alcohol)\b", name, re.I):
        tags.add("alcohol")
    if category in {"grain", "legume"}:
        tags.add("staple")
    if category == "grain" and re.search(
        r"\b(bajra|jowar|ragi|samai|varagu|millet|kodo|kutki)\b", name, re.I
    ):
        tags.add("millet")
    return sorted(tags)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def curate_indian_food_db(ingredients: list[dict[str, object]] | None = None) -> tuple[pd.DataFrame, IndianBuildReport]:
    """Assemble the final Indian food table (ingredients + dishes)."""
    ingredients = ingredients if ingredients is not None else load_ifct_table()
    dishes = _compose_dishes(ingredients)
    rows = ingredients + dishes

    records: list[dict[str, object]] = []
    for row in rows:
        category = _category(str(row["grup"]))
        allowed, default = _forms(category)
        records.append(
            {
                "fdc_id": str(row["fdc_id"]),
                "name": str(row["name"]),
                "category": category,
                "fdc_category": str(row["grup"]),
                "data_type": "ifct2017",
                "hazard_class": _hazard(str(row["name"]), category),
                "default_form": default,
                "allowed_forms": json.dumps(allowed),
                "tags": json.dumps(_tags(row, category)),
                **{n: float(row[n]) for n in NUTRIENTS},
            }
        )

    frame = pd.DataFrame(records)
    frame = frame.drop_duplicates(subset="fdc_id", keep="first")
    frame = frame.sort_values("name", kind="stable").reset_index(drop=True)

    slot_counts: Counter[str] = Counter()
    diet_counts: Counter[str] = Counter()
    for tags in frame["tags"]:
        for t in json.loads(tags):
            if t.startswith("meal_"):
                slot_counts[t.removeprefix("meal_")] += 1
            elif t.startswith("diet_"):
                diet_counts[t.removeprefix("diet_")] += 1

    report = IndianBuildReport(
        n_ifct_rows=len(ingredients),
        n_dishes=len(dishes),
        n_final=len(frame),
        category_counts=dict(Counter(frame["category"]).most_common()),
        slot_counts=dict(slot_counts.most_common()),
        diet_counts=dict(diet_counts.most_common()),
        nutrient_coverage={
            n: round(float((frame[n] > 0).mean()), 4) for n in NUTRIENTS
        },
    )
    return frame, report
