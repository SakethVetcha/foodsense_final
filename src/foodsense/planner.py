"""Indian meal planner for ages 5-20.

Given who is eating (age, sex, optional weight, diet, goal, optional lab values),
this builds a full day of Indian meals -- **breakfast, lunch, dinner and snacks**
-- portioned to that person's ICMR-NIN 2020 requirements, and reports the
nutrient proportions of every meal and of the whole day.

Design choices, and why they differ from the four-stage counterfactual pipeline
------------------------------------------------------------------------------
The counterfactual pipeline *edits a meal the user already has*. A meal planner
has no starting meal: it builds one from the food database. So instead of a
differential-evolution search with a surrogate objective, this is a deterministic
role-based constructor:

1. Each slot has **roles** -- a staple, a protein dish, a vegetable, an
   accompaniment -- and each role has a pool of real Indian dishes/ingredients
   (from ``data/processed/indian_food_db``, either an IFCT ingredient or one of
   the composite dishes in :mod:`foodsense.data.indian_dishes`).
2. Candidate pools are filtered by the user's **diet** (vegetarian / eggetarian /
   non-vegetarian) and any excluded tags, then **ranked** by preferences from the
   goal and any lab findings (iron-rich first if haemoglobin is low, low-GI first
   for glycemic control, and so on). Ranking is deterministic under the seed.
3. Portions are set so each meal carries its **share of the day** (breakfast 25%,
   lunch 30%, dinner 30%, snacks 15% of energy), with the staple scaled to the
   slot's energy and the protein/vegetable roles sized to close the protein and
   fibre gaps.

The result is fully reproducible for a given seed and profile, and every number
is a straight recomputation from the IFCT database -- so the plan is "verified"
in the same sense Stage 4 uses the word, without needing a separate verifier pass.
"""

from __future__ import annotations

import random
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from foodsense.constraints.goals import (
    Threshold,
    energy_shares,
    estimate_added_sugars,
    estimate_glycemic_load,
    satisfaction,
)
from foodsense.data.fdc import FoodDB, FoodRecord, get_indian_food_db
from foodsense.labs import LabReport, analyze_lab_text
from foodsense.nutrition import (
    MEAL_SLOTS,
    SLOT_ENERGY_SHARE,
    daily_source,
    daily_values,
    daily_targets,
    energy_target,
    life_stage_for_age,
    load_life_stage_config,
    reference_weight_kg,
    slot_targets,
)
from foodsense.schemas import Form, LifeStage, MealItem, NutrientVector, Sex

__all__ = [
    "NUTRIENT_LABELS",
    "Activity",
    "DietType",
    "Goal",
    "MealPlan",
    "PlanItem",
    "PlannedMeal",
    "PlannerProfile",
    "generate_meal_plan",
    "get_food_alternatives",
    "recalculate_meal_plan",
]

#: How hard the soft-margin scoring is bent. Matches the pipeline's rule engine.
_SOFTNESS = 0.15

#: Human labels and units for the nutrients the dashboard shows.
NUTRIENT_LABELS: dict[str, tuple[str, str]] = {
    "energy_kcal": ("Energy", "kcal"),
    "protein_g": ("Protein", "g"),
    "carbohydrate_g": ("Carbohydrate", "g"),
    "fat_g": ("Fat", "g"),
    "fiber_g": ("Dietary fibre", "g"),
    "saturated_fat_g": ("Saturated fat", "g"),
    "added_sugars_g": ("Added sugars", "g"),
    "calcium_mg": ("Calcium", "mg"),
    "iron_mg": ("Iron", "mg"),
    "zinc_mg": ("Zinc", "mg"),
    "magnesium_mg": ("Magnesium", "mg"),
    "potassium_mg": ("Potassium", "mg"),
    "sodium_mg": ("Sodium", "mg"),
    "vitamin_c_mg": ("Vitamin C", "mg"),
    "vitamin_a_rae_ug": ("Vitamin A", "µg"),
    "folate_dfe_ug": ("Folate", "µg"),
    "vitamin_d_ug": ("Vitamin D", "µg"),
}

#: Order the nutrient table and charts are rendered in.
DISPLAY_ORDER: tuple[str, ...] = (
    "energy_kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "fiber_g",
    "saturated_fat_g",
    "added_sugars_g",
    "sodium_mg",
    "calcium_mg",
    "iron_mg",
    "zinc_mg",
    "magnesium_mg",
    "potassium_mg",
    "vitamin_c_mg",
    "vitamin_a_rae_ug",
    "folate_dfe_ug",
    "vitamin_d_ug",
)


#: Diet classes, energy goals and ICMR activity classes.
DietType = Literal["vegetarian", "eggetarian", "non_vegetarian"]
GoalName = Literal["balanced", "glycemic_control", "weight_management"]
Activity = Literal["sedentary", "moderate", "heavy"]

#: Energy multipliers around the ICMR moderate-activity reference.
_ACTIVITY_FACTOR: dict[str, float] = {"sedentary": 0.90, "moderate": 1.00, "heavy": 1.15}


class PlannerProfile(BaseModel):
    """Who the plan is for, and what it should respect."""

    model_config = ConfigDict(extra="forbid")

    age_years: int = Field(..., ge=5, le=20, description="Age in years (5-20).")
    sex: Sex = Field(..., description="Biological sex; drives iron/energy targets.")
    weight_kg: float | None = Field(default=None, gt=0, le=200, description="Body weight in kg (optional).")
    height_cm: float | None = Field(default=None, gt=40, le=250, description="Height in cm (optional).")
    activity: Activity = "moderate"
    diet: DietType = "vegetarian"
    regional_preference: str = Field(
        default="all",
        description="Regional food preference: all, north_indian, south_indian, west_indian, east_indian.",
    )
    goal: GoalName = "balanced"
    health_flags: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(
        default_factory=list,
        description="Allergies to exclude: gluten, dairy, peanuts, nuts, eggs, soy, etc.",
    )
    exclude_tags: list[str] = Field(
        default_factory=list, description="Food tags to avoid (e.g. ['gluten'])."
    )
    likes: list[str] = Field(
        default_factory=list, description="Preferred dishes or ingredients to prioritize."
    )
    dislikes: list[str] = Field(
        default_factory=list, description="Disliked foods to avoid."
    )
    lab_text: str | None = Field(
        default=None, description="Optional pasted/uploaded lab-report text."
    )
    note: str | None = None


class PlanItem(BaseModel):
    """One food in a meal, with its contribution."""

    model_config = ConfigDict(extra="forbid")

    food_id: str
    name: str
    category: str
    quantity_g: float
    form: str
    is_dish: bool = False
    nutrients: NutrientVector


class PlannedMeal(BaseModel):
    """One meal slot: its items, its totals and its share of the day."""

    model_config = ConfigDict(extra="forbid")

    slot: str
    title: str
    items: list[PlanItem]
    nutrients: NutrientVector
    energy_kcal: float
    energy_share_of_day: float
    macro_shares: dict[str, float]
    compliance: float = Field(..., ge=0.0, le=1.0)
    glycemic_load: float = 0.0
    note: str = ""


class NutrientStatus(BaseModel):
    """One row of the day's nutrient-vs-target table."""

    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    unit: str
    target: float | None
    actual: float
    pct: float | None = None
    kind: Literal["floor", "ceiling", "band"]
    #: The acceptable range, in this row's unit, when ``kind`` is ``band``. Fat
    #: has no single target -- it has a band, and 20% or 34% of energy are both
    #: fine -- so the dashboard judges a band row by whether it lands inside,
    #: rather than by how far it got towards a midpoint that is not a goal.
    band_low: float | None = None
    band_high: float | None = None


class MealPlan(BaseModel):
    """The whole day: four meals, the day's totals and the traceability info."""

    model_config = ConfigDict(extra="forbid")

    profile: PlannerProfile
    life_stage: LifeStage
    life_stage_label: str
    sex: Sex
    reference_weight_kg: float
    source: str
    energy_target_kcal: float
    meals: list[PlannedMeal]
    day_nutrients: NutrientVector
    day_macro_shares: dict[str, float]
    day_glycemic_load: float
    day_compliance: float = Field(..., ge=0.0, le=1.0)
    nutrient_table: list[NutrientStatus]
    insights: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    lab_report: LabReport | None = None
    seed: int
    runtime_s: float = 0.0
    verified: bool = Field(
        default=True,
        description=(
            "True because every figure is a recomputation from the IFCT 2017 "
            "food database rather than a generated claim."
        ),
    )


# ---------------------------------------------------------------------------
# Candidate pools: roles per slot, as pinned food ids
# ---------------------------------------------------------------------------

_STAPLES: dict[str, tuple[str, ...]] = {
    # Only dishes (X-prefixed) are offered as a staple: a raw IFCT row like
    # "Wheat flour, atta" is not a thing a person is served.
    "breakfast": ("X001", "X002", "X003", "X004", "X005", "X006", "X007"),
    "lunch": ("X030", "X005", "X047", "X046", "X041", "X040", "X039"),
    # Dosa and curd rice are ordinary dinners in the south; including them keeps
    # the pool wide enough that a dish used at lunch is not forced back at dinner.
    "dinner": ("X005", "X030", "X047", "X046", "X041", "X040", "X039", "X002"),
    # A tiffin-snack, not a meal: poha, upma, idli and dosa are all things an
    # Indian household eats between meals. More than one, because a single-item
    # pool forces the same dish back at snack time whenever breakfast used it.
    "snacks": ("X004", "X003", "X001", "X002"),
}

_PROTEINS: dict[str, tuple[str, ...]] = {
    "breakfast": ("X008", "X022", "L002", "X021", "H012"),
    "lunch": ("X031", "X032", "X033", "X034", "X037", "X039", "X042", "X043", "X044", "X045"),
    "dinner": ("X032", "X031", "X033", "X034", "X037", "X044", "X043", "X042", "X045"),
    # Chana, sprouts and dairy lead; nuts are last because a protein-sized
    # portion of nuts is a fat-sized portion of nuts.
    "snacks": ("X021", "X020", "X022", "L002", "H001", "H012"),
}

#: Maximum grams a role may reach, so no single role dominates a plate.
_ROLE_MAX_G: dict[str, float] = {"staple": 300.0, "protein": 160.0, "vegetable": 180.0, "snack": 160.0}

#: A nut/oil-seed portion is a handful, whatever the protein gap says.
_NUT_MAX_G = 30.0

#: The dairy serving that anchors a child's day when nothing else on the plate is
#: dairy. ICMR-NIN 2020 recommends 300-500 ml of milk or its equivalent daily for
#: 5-20 y; a glass with the evening snack is the part of that the planner can
#: guarantee, and it is the only dietary vitamin D and B12 a vegetarian Indian
#: day is likely to see at all.
#: Milk, not paneer: a glass is what the guidance is about, and paneer carries
#: 0.13 ug of vitamin D per 100 g against milk's 1.2 -- the serving is there for
#: the D and the B12, so the drink is what belongs in the pool.
_DAIRY_SERVING: tuple[str, ...] = ("L002", "L001")
_DAIRY_SERVING_G = 200.0

_VEGETABLES: dict[str, tuple[str, ...]] = {
    "breakfast": ("X023", "E009", "E001", "E028"),
    "lunch": ("X036", "X038", "X035", "C033", "X037"),
    "dinner": ("X038", "X036", "X035", "C033"),
    "snacks": ("E009", "E001", "E028", "E055", "E049", "E065"),
}

#: Cereal staples split into the two groups a thali pairs: a rice dish and a
#: bread/ball of another grain. A large-energy slot gets **one of each** -- roti
#: *and* rice is what a real plate looks like, and it keeps a single dish from
#: having to grow to an unrealistic portion to carry the whole slot.
_CEREAL_GROUPS: dict[str, tuple[str, ...]] = {
    "rice": ("X030", "X040", "X041", "X039"),
    "grain": ("X005", "X006", "X047", "X002", "X046"),
}

_GROUP_OF_CEREAL: dict[str, str] = {
    food_id: group for group, ids in _CEREAL_GROUPS.items() for food_id in ids
}

#: Slot energy (kcal) above which a second cereal is added. Below this one dish
#: is a realistic portion; above it, one dish would be a bowl the size of a head.
_SECOND_CEREAL_AT: dict[str, float] = {
    "breakfast": 900.0,
    "lunch": 850.0,
    "dinner": 850.0,
    # A 500+ kcal snack for an active teenager is poha or a roti, not just fruit.
    "snacks": 350.0,
}

#: Snack energy (kcal) above which a second snack item is added. A fruit and a
#: fistful of chana top out around 250 kcal; an active teenager's tiffin is well
#: over 400, and one swollen portion is not what that looks like on a plate.
_SECOND_SNACK_AT = 300.0

#: Fraction of the slot budget the second cereal aims at.
_COMPLEMENT_SHARE: dict[str, float] = {
    "breakfast": 0.20,
    "lunch": 0.25,
    "dinner": 0.25,
    "snacks": 0.30,
}

#: Diet classes a food of each class is compatible with.
_DIET_COMPATIBLE: dict[str, frozenset[str]] = {
    "vegetarian": frozenset({"vegetarian"}),
    "eggetarian": frozenset({"vegetarian", "eggetarian"}),
    "non_vegetarian": frozenset({"vegetarian", "eggetarian", "non_vegetarian"}),
}

#: Fraction of a slot's energy the staple role is aimed at.
_STAPLE_ENERGY_SHARE: dict[str, float] = {
    "breakfast": 0.55,
    "lunch": 0.45,
    "dinner": 0.45,
    "snacks": 0.30,
}

#: Cooking oils offered as an explicit plate item. IFCT composition describes a
#: food as it is, and a sabzi or a dal is cooked in oil -- without it a
#: vegetarian Indian plate reads a few points of energy low on fat. The oil is
#: shown on the plate rather than folded in silently, so the entry is auditable
#: and the totals are the sum of what is listed.
_COOKING_FATS: tuple[str, ...] = ("T005", "T012", "T006", "T013")

#: Share of energy the top-up aims for: the band's minimum plus this margin, so
#: the day lands inside the band rather than on its edge.
_FAT_MARGIN = 0.03

#: A teaspoon of oil. Nothing smaller is a real pour, so a meal either gets at
#: least this much or none of the top-up: "groundnut oil, 2 g" on a plate would be
#: a number produced by arithmetic rather than by cooking.
#: Smallest portion of oil worth putting on a plate: a teaspoon, and the half
#: teaspoon used for the last nudge when a day is already almost in band.
_TSP_G = 5.0
_HALF_TSP_G = 2.5

#: Default gram servings used to seed each role before scaling.
_BASE_SERVING_G: dict[str, float] = {"staple": 80.0, "protein": 120.0, "vegetable": 90.0, "snack": 100.0}

#: Portion clamps, grams.
_MIN_G, _MAX_G = 10.0, 400.0


def _round_g(value: float) -> float:
    """Round a portion to the nearest 5 g, never below the presence floor."""
    return max(_MIN_G, round(value / 5.0) * 5.0)


class _MealBuilder:
    """Stateful helper that assembles one meal against its slot targets."""

    def __init__(
        self,
        db: FoodDB,
        slot: str,
        energy_budget: float,
        thresholds: dict[str, Threshold],
        diet: str,
        exclude_tags: set[str],
        preference: frozenset[str],
        avoid: frozenset[str],
        rng: random.Random,
        day_used: set[str] | None = None,
    ) -> None:
        self.db = db
        self.slot = slot
        self.energy_budget = energy_budget
        self.thresholds = thresholds
        self.diet = diet
        self.exclude_tags = exclude_tags
        self.preference = preference
        self.avoid = avoid
        self.rng = rng
        #: Dishes already on the day's other plates. Nobody wants the same sabzi
        #: at lunch and dinner, so these are avoided -- but only skipped while a
        #: real alternative exists (see :meth:`_pick`).
        self.day_used = day_used if day_used is not None else set()
        self.items: list[MealItem] = []
        self.notes: list[str] = []
        #: Which cereal group the main staple came from, so the complement can
        #: deliberately be the other one.
        self.staple_group: str | None = None

    # -- candidate resolution ------------------------------------------------

    def _pick(
        self, pool: tuple[str, ...], role: str, *, allow_repeat: bool = True
    ) -> FoodRecord | None:
        """Best food from ``pool`` for the user, or ``None`` if none qualifies.

        Ranking is (preference tags matched, role quality). Role quality matters:
        a *staple* should carry energy, but a *protein* role is ranked by protein
        per 100 kcal rather than protein per 100 g, otherwise nuts -- which are
        protein-dense and calorie-dense -- win every protein slot and turn a
        snack into a fat bomb.
        """
        viable = self._candidates(pool, role, block_day_used=True)
        if not viable and allow_repeat:
            # Repeating a dish is worse than nothing only when there really is
            # nothing else the diet and exclusions allow, so relax the day filter
            # before giving up on the role. Roles that pass ``allow_repeat=False``
            # are the ones where a repeat is more jarring than a gap -- a second
            # bajra roti at dinner when it was already at lunch.
            viable = self._candidates(pool, role, block_day_used=False)
        if not viable:
            return None
        best = max(v[0] for v in viable)
        top = [v for v in viable if v[0] == best]
        # A little seeded variation among equally-preferred options keeps two
        # different seeds from producing identical days without hurting ranking.
        top.sort(key=lambda v: (-v[1], v[2]))
        return self.rng.choice(top[: min(3, len(top))])[3]

    def _is_excluded(self, record: FoodRecord) -> bool:
        all_avoid = self.avoid | self.exclude_tags
        if not all_avoid:
            return False
        if all_avoid & record.tags:
            return True
        name_lower = record.name.lower()
        for tag in all_avoid:
            t = tag.lower().strip()
            if not t:
                continue
            if t in ("gluten", "wheat") and any(
                w in name_lower
                for w in ("roti", "atta", "paratha", "upma", "dalia", "wheat", "suji", "semolina")
            ):
                return True
            if t in ("dairy", "lactose") and (
                any(w in name_lower for w in ("milk", "paneer", "curd", "dahi", "ghee"))
                or record.category == "dairy"
            ):
                return True
            if t in ("nuts", "peanuts", "peanut") and (
                any(w in name_lower for w in ("nut", "almond", "cashew", "peanut", "walnut"))
                or record.category == "nut_seed"
            ):
                return True
            if t in ("egg", "eggs") and (
                any(w in name_lower for w in ("egg", "omelette"))
                or record.category == "egg"
            ):
                return True
            if t in ("soy", "soya") and any(w in name_lower for w in ("soy", "soya")):
                return True
            if len(t) > 3 and t in name_lower:
                return True
        return False

    def _candidates(
        self, pool: tuple[str, ...], role: str, *, block_day_used: bool
    ) -> list[tuple[int, float, str, FoodRecord]]:
        """Every food in ``pool`` the user may be served, with its rank inputs."""
        viable: list[tuple[int, float, str, FoodRecord]] = []
        compatible = _DIET_COMPATIBLE[self.diet]
        used = {i.food_id for i in self.items}
        for food_id in pool:
            record = self.db.find(food_id)
            if record is None:
                continue
            if food_id in used:
                continue  # never two portions of the same dish at one meal
            if block_day_used and food_id in self.day_used:
                continue
            if self._is_excluded(record):
                continue
            if record.category == "prepared":
                # Composite dish: its diet class is carried as a diet_* tag.
                diet = next(
                    (t.removeprefix("diet_") for t in record.tags if t.startswith("diet_")),
                    "vegetarian",
                )
                if diet not in compatible:
                    continue
            if self.avoid & record.tags:
                continue
            score = len(self.preference & record.tags)
            name_lower = record.name.lower()
            for pref in self.preference:
                if len(pref) > 3 and pref in name_lower:
                    score += 2
            quality = _role_quality(role, record)
            viable.append((score, quality, food_id, record))
        return viable

    def _add(self, record: FoodRecord, grams: float) -> MealItem:
        form = record.default_form
        item = record.as_item(_round_g(grams), form)
        self.items.append(item)
        self.day_used.add(item.food_id)
        return item

    def _energy_of(self, grams: float, record: FoodRecord) -> float:
        return record.nutrients_per_100g.energy_kcal * grams / 100.0

    # -- roles ---------------------------------------------------------------

    def add_staple(self, energy_share: float | None = None) -> None:
        record = self._pick(_STAPLES[self.slot], "staple")
        if record is None:
            return
        share = _STAPLE_ENERGY_SHARE[self.slot] if energy_share is None else energy_share
        target = self.energy_budget * share
        kcal_per_g = max(record.nutrients_per_100g.energy_kcal / 100.0, 0.5)
        grams = min(max(target / kcal_per_g, 40.0), 260.0)
        self._add(record, grams)
        self.staple_group = _GROUP_OF_CEREAL.get(record.fdc_id, self.staple_group)

    def add_complementary_cereal(self, energy_share: float) -> None:
        """The other cereal of the pair: roti if the staple was rice, else rice.

        Only the dishes this slot actually offers are eligible, so a
        lunch-or-dinner dish never appears at breakfast.
        """
        other = "grain" if self.staple_group == "rice" else "rice"
        allowed = set(_STAPLES[self.slot])
        pool = tuple(f for f in _CEREAL_GROUPS[other] if f in allowed and self.db.find(f))
        if not pool:
            return
        record = self._pick(pool, "staple", allow_repeat=False)
        if record is None:
            return
        target = self.energy_budget * energy_share
        kcal_per_g = max(record.nutrients_per_100g.energy_kcal / 100.0, 0.5)
        self._add(record, min(max(target / kcal_per_g, 40.0), 200.0))

    def add_protein(self) -> None:
        record = self._pick(_PROTEINS[self.slot], "protein")
        if record is None:
            return
        protein_floor = self.thresholds.get("protein_g")
        want = (protein_floor.minimum if protein_floor and protein_floor.minimum else 8.0)
        have = self._totals().protein_g
        gap = max(want - have, 0.0)
        per_g = record.nutrients_per_100g.protein_g / 100.0
        if per_g <= 0.01:
            grams = _BASE_SERVING_G["protein"]
        else:
            grams = min(max(gap / per_g, 40.0), _ROLE_MAX_G["protein"])
        if record.category == "nut_seed":
            grams = min(grams, _NUT_MAX_G)
        self._add(record, grams)
        if "iron_rich" in record.tags:
            self.notes.append(f"{record.name} is iron-rich, which helps the iron target.")

    def add_vegetable(self) -> None:
        record = self._pick(_VEGETABLES[self.slot], "vegetable")
        if record is None:
            return
        self._add(record, _ROLE_MAX_G["vegetable"] * 0.55)

    def add_dairy_serving(self) -> None:
        """A glass of milk or a bowl of curd, when the day has no dairy yet."""
        if any(av in ("dairy", "lactose") for av in (self.avoid | self.exclude_tags)):
            return
        if any(
            (record := self.db.find(food_id)) is not None and record.category == "dairy"
            for food_id in self.day_used
        ):
            return
        pool = tuple(f for f in _DAIRY_SERVING if self.db.find(f))
        record = self._pick(pool, "protein")
        if record is None:
            return
        self._add(record, _DAIRY_SERVING_G)

    def add_snack(self, *, allow_repeat: bool = True) -> None:
        pool = tuple(t for t in _VEGETABLES["snacks"] if self.db.find(t))
        record = self._pick(pool, "snack", allow_repeat=allow_repeat)
        if record is None:
            return
        self._add(record, _BASE_SERVING_G["snack"])

    # -- accounting ----------------------------------------------------------

    def _totals(self) -> NutrientVector:
        return self.db.nutrients_for(self.items)

    def rescale_to_energy(self) -> None:
        """Scale every portion so the meal lands on its energy budget.

        Scaling the whole plate rather than just the staple preserves the
        proportions the roles were chosen for, which is what keeps the macro
        split meaningful. Bounded to [0.5x, 1.6x] so a tiny role cannot explode,
        and nut/oil-seed portions are re-clamped afterwards -- a handful stays a
        handful however much energy the slot still needs. A snack gets a wider
        upper bound, because its roles are low-energy-density by nature: two
        fruits and a bowl of chana is a real tiffin, and the alternative -- a
        snack that cannot reach its share of the day -- is what showed up as
        every snack bar sitting below its target.
        """
        if not self.items:
            return
        total = self._totals().energy_kcal
        if total <= 0 or self.energy_budget <= 0:
            return
        cap = 2.0 if self.slot == "snacks" else 1.6
        factor = min(max(self.energy_budget / total, 0.5), cap)
        rescaled: list[MealItem] = []
        for item in self.items:
            grams = min(max(item.quantity_g * factor, _MIN_G), _MAX_G)
            record = self.db.find(item.food_id)
            if record is not None and record.category == "nut_seed":
                grams = min(grams, _NUT_MAX_G)
            rescaled.append(item.model_copy(update={"quantity_g": _round_g(grams)}))
        self.items = rescaled


def _cooking_oil(
    db: FoodDB, diet: str, avoid: frozenset[str], exclude_tags: set[str]
) -> FoodRecord | None:
    """The oil this user's kitchen would use, in a fixed preference order.

    Fixed rather than seeded on purpose: the oil is a property of the household,
    not of the day, so two seeds should not disagree about what is in the pan.
    """
    compatible = _DIET_COMPATIBLE[diet]
    for food_id in _COOKING_FATS:
        record = db.find(food_id)
        if record is None:
            continue
        if exclude_tags & record.tags or avoid & record.tags:
            continue
        tagged = next(
            (t.removeprefix("diet_") for t in record.tags if t.startswith("diet_")),
            "vegetarian",
        )
        if tagged not in compatible:
            continue
        return record
    return None


def _top_up_cooking_fat(
    meals: list[PlannedMeal],
    db: FoodDB,
    *,
    fat_band: Threshold | None,
    slot_thresholds: dict[str, dict[str, Threshold]],
    day_energy_target: float,
    visible_fat_max_g: float,
    oil: FoodRecord | None,
) -> list[PlannedMeal]:
    """Put the cooking oil back on a day that landed below the fat band.

    IFCT composition is per 100 g of the food itself; a sabzi, a dal and a roti
    are all cooked in oil, and a plan built only from composition tables reads a
    few points of energy low on fat -- most visibly on vegetarian plates, which
    have no meat fat to carry the difference.

    The oil is added as a **visible plate item**, distributed across the cooked
    meals by their share of the day, and the day is then only topped up as far as
    the band's lower edge plus a margin. It is capped by the life stage's own
    visible-fat guidance, so this can never talk the plan into more fat than
    ICMR-NIN suggests, and it does nothing at all when the band is already met.

    The other items in each meal are scaled down by exactly the energy the oil
    contributes, so the day still lands on its target: this changes what the
    energy is made of, never how much of it there is.
    """
    if fat_band is None or fat_band.minimum is None or oil is None or not meals:
        return meals
    day = NutrientVector.sum([m.nutrients for m in meals])
    energy = day.energy_kcal
    if energy <= 0:
        return meals
    fat_kcal = day.fat_g * 9.0
    # Nothing to do when the day is already inside the band, even at its floor:
    # the oil is a correction, not a way to push every day to the same number.
    if fat_kcal / energy >= fat_band.minimum:
        return meals
    # Aim past the floor by a margin, because adding the oil scales the rest of
    # the plate down by the same energy -- the gain in share is smaller than the
    # deficit, and aiming exactly at the floor leaves the day a point short.
    aim = min(fat_band.minimum + _FAT_MARGIN, fat_band.maximum or 1.0)
    deficit_kcal = aim * energy - fat_kcal
    if deficit_kcal <= 0:
        return meals
    grams = min(deficit_kcal / 9.0, visible_fat_max_g)
    if grams < 1.0:
        return meals  # close enough to the band that the arithmetic is noise

    cooked = [m for m in meals if m.slot != "snacks" and m.items]
    if not cooked:
        return meals
    total_share = sum(SLOT_ENERGY_SHARE[m.slot] for m in cooked)

    # A teaspoon is the smallest sensible amount of oil, but three teaspoons at
    # once overshoot a small deficit: a day 0.3 points below the band needs about
    # 5 g, and flooring every cooked meal at a teaspoon put 15 g on it and took
    # the day 6 points past the band. So hand out teaspoons only while the budget
    # can pay for them, largest meal first.
    portions: dict[str, float] = {}
    remaining = grams
    shares = sorted(
        ((m, SLOT_ENERGY_SHARE[m.slot] / total_share) for m in cooked),
        key=lambda pair: -pair[1],
    )
    for meal, share in shares:
        if remaining < _HALF_TSP_G - 1e-9:
            break
        # The last spoon may be a half: a day two points under the band needs a
        # nudge, and withholding it entirely leaves the day out of band.
        floor = _TSP_G if remaining >= _TSP_G else _HALF_TSP_G
        take = min(max(floor, float(round(grams * share))), remaining)
        portions[meal.slot] = take
        remaining -= take

    out: list[PlannedMeal] = []
    for meal in meals:
        portion = portions.get(meal.slot, 0.0)
        if portion <= 0:
            out.append(meal)
            continue
        item = oil.as_item(portion, oil.default_form)
        oil_kcal = db.nutrients_for_item(item).energy_kcal
        budget = day_energy_target * SLOT_ENERGY_SHARE[meal.slot]
        food_kcal = meal.nutrients.energy_kcal
        # Shrink the food by exactly what the oil adds, so energy stays on target.
        factor = (budget - oil_kcal) / food_kcal if food_kcal > 0 else 1.0
        factor = min(max(factor, 0.5), 1.0)
        items: list[PlanItem] = []
        for old in meal.items:
            grams_after = _round_g(old.quantity_g * factor)
            as_item = MealItem(
                food_id=old.food_id,
                name=old.name,
                quantity_g=grams_after,
                form=Form(old.form),
            )
            items.append(
                PlanItem(
                    food_id=old.food_id,
                    name=old.name,
                    category=old.category,
                    quantity_g=grams_after,
                    form=old.form,
                    is_dish=old.is_dish,
                    nutrients=db.nutrients_for_item(as_item),
                )
            )
        items.append(
            PlanItem(
                food_id=item.food_id,
                name=item.name,
                category=oil.category,
                quantity_g=item.quantity_g,
                form=item.form.value,
                nutrients=db.nutrients_for_item(item),
            )
        )
        nutrients = NutrientVector.sum([i.nutrients for i in items])
        thresholds = slot_thresholds.get(meal.slot, {})
        meal_items = [
            MealItem(
                food_id=i.food_id, name=i.name, quantity_g=i.quantity_g, form=Form(i.form)
            )
            for i in items
        ]
        compliance, _ = _compliance(
            nutrients, thresholds, estimate_added_sugars(meal_items, db)
        )
        note = (
            f"Includes {item.quantity_g:g} g of {oil.name.lower()} for cooking, "
            "which IFCT's composition tables do not carry."
        )
        out.append(
            meal.model_copy(
                update={
                    "items": items,
                    "nutrients": nutrients,
                    "energy_kcal": round(nutrients.energy_kcal, 1),
                    "macro_shares": _macro_shares(nutrients),
                    "compliance": round(compliance, 4),
                    "glycemic_load": round(estimate_glycemic_load(meal_items, db), 2),
                    "note": f"{meal.note} {note}".strip(),
                }
            )
        )
    return out


def _role_quality(role: str, record: FoodRecord) -> float:
    """A role-appropriate quality score used to break ties between candidates."""
    per_100g = record.nutrients_per_100g
    energy = per_100g.energy_kcal
    if role == "staple":
        return energy  # a staple should actually carry energy
    if role == "protein":
        return per_100g.protein_g / (energy / 100.0) if energy > 0 else per_100g.protein_g
    # vegetable / snack: fibre per 100 kcal, so a low-calorie vegetable is not
    # penalised against a calorie-dense one.
    return per_100g.fiber_g / (energy / 100.0) if energy > 0 else per_100g.fiber_g


def _compliance(
    nutrients: NutrientVector,
    thresholds: dict[str, Threshold],
    added_sugars: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """Weighted soft-margin compliance of a meal against its targets."""
    numerator = 0.0
    denominator = 0.0
    per_rule: dict[str, float] = {}
    metrics: dict[str, float] = dict(nutrients.as_dict())
    metrics["added_sugars_g"] = added_sugars  # documented proxy, see goals.py
    shares = energy_shares(nutrients)
    for macro, value in shares.items():
        metrics[f"share:{macro}"] = value

    for key, threshold in thresholds.items():
        value = metrics.get(key)
        if value is None:
            continue
        score = satisfaction(value, threshold, _SOFTNESS)
        per_rule[key] = score
        numerator += score * threshold.weight
        denominator += threshold.weight
    return (numerator / denominator if denominator else 1.0), per_rule


def _macro_shares(nutrients: NutrientVector) -> dict[str, float]:
    shares = energy_shares(nutrients)
    return {k.removesuffix("_g"): round(v, 4) for k, v in shares.items()}


def _preferences(
    profile: PlannerProfile, life_stage: LifeStage, lab_report: LabReport | None
) -> tuple[frozenset[str], frozenset[str]]:
    """Derive food-tag preferences and avoidances from goal, flags and labs."""
    preference: set[str] = set()
    avoid: set[str] = set()

    # Adolescent girls carry a much higher iron RDA, so the plan leans iron-rich
    # by default rather than only when a lab value says so.
    if profile.sex is Sex.FEMALE and life_stage in (
        LifeStage.PRETEEN_10_12,
        LifeStage.TEEN_13_15,
        LifeStage.TEEN_16_18,
        LifeStage.YOUNG_ADULT_19_20,
    ):
        preference |= {"iron_rich"}

    if profile.goal == "glycemic_control":
        preference |= {"high_fibre", "millet", "easily_digested"}
    if profile.goal == "weight_management":
        preference |= {"high_fibre", "high_protein"}
        avoid |= {"added_sugar_source"}
    if profile.diet == "vegetarian":
        preference |= {"dairy"}

    flags = set(profile.health_flags)
    if "iron_focus" in flags:
        preference |= {"iron_rich"}
    if "hypertension" in flags:
        avoid |= {"high_sodium"}
    if "low_saturated_fat" in flags:
        avoid |= {"ghee_heavy"}
    if "diabetes" in flags:
        preference |= {"high_fibre", "millet"}

    if lab_report is not None:
        focuses = {f for finding in lab_report.findings for f in finding.dietary_focus}
        if "iron_focus" in focuses:
            preference |= {"iron_rich"}
        if "calcium_focus" in focuses:
            preference |= {"calcium_rich", "dairy"}
        if "glycemic_control" in focuses:
            preference |= {"high_fibre", "millet"}
            avoid |= {"added_sugar_source"}
        if "low_saturated_fat" in focuses:
            avoid |= {"ghee_heavy"}
        if "high_fibre" in focuses:
            preference |= {"high_fibre"}
        if "vitamin_d_focus" in focuses:
            # Diet is a partial lever for vitamin D; the calcium-rich dairy foods
            # here are the dietary half of the answer, and the insight text says
            # so rather than implying a meal plan fixes it.
            preference |= {"calcium_rich", "dairy"}
        if "vitamin_b12_focus" in focuses:
            # B12 rides on animal foods -- milk, curd, egg, fish -- so for a
            # vegetarian plan the dairy and high-protein pools are what can
            # actually move the number.
            preference |= {"dairy", "high_protein", "calcium_rich"}
        if "healthy_fats" in focuses:
            avoid |= {"ghee_heavy"}

    for tag in profile.exclude_tags:
        avoid.add(tag.lower().strip())

    for allergy in profile.allergies:
        a = allergy.lower().strip()
        if not a:
            continue
        avoid.add(a)
        if "gluten" in a or "wheat" in a:
            avoid.add("gluten")
        if "dairy" in a or "lactose" in a or "milk" in a:
            avoid.add("dairy")
        if "peanut" in a or "nut" in a:
            avoid.add("nuts")
        if "egg" in a:
            avoid.add("egg")
        if "soy" in a:
            avoid.add("soy")

    for dislike in profile.dislikes:
        d = dislike.lower().strip()
        if d:
            avoid.add(d)

    if profile.regional_preference and profile.regional_preference != "all":
        reg = profile.regional_preference.lower().strip()
        preference.add(reg)
        if not reg.endswith("_indian"):
            preference.add(f"{reg}_indian")

    for like in profile.likes:
        l = like.lower().strip()
        if l:
            preference.add(l)

    return frozenset(preference), frozenset(avoid)


def _insights(
    profile: PlannerProfile,
    life_stage: LifeStage,
    values: dict[str, float],
    day: NutrientVector,
    lab_report: LabReport | None,
) -> list[str]:
    """Human-readable notes drawn from the biggest gaps and the lab findings."""
    notes: list[str] = []
    if profile.height_cm and profile.weight_kg:
        from foodsense.nutrition import calculate_body_metrics

        bm = calculate_body_metrics(
            profile.age_years, profile.sex, profile.height_cm, profile.weight_kg
        )
        if bm.get("bmi") and bm.get("bmi_category"):
            notes.append(
                f"Body Mass Index (BMI): {bm['bmi']} kg/m² ({bm['bmi_category']}). "
                f"Estimated basal metabolic rate is ~{bm['estimated_bmr_kcal']} kcal/day."
            )
    if profile.sex is Sex.FEMALE and life_stage in (
        LifeStage.PRETEEN_10_12,
        LifeStage.TEEN_13_15,
        LifeStage.TEEN_16_18,
        LifeStage.YOUNG_ADULT_19_20,
    ):
        notes.append(
            f"Iron requirement for girls at this stage is {values.get('iron_mg', 0):g} mg/day "
            "(ICMR-NIN 2020), well above the boys' value because of menstrual losses. "
            "The plan leans on dal, leafy greens and jaggery to meet it."
        )
    iron_pct = _pct(day.iron_mg, values.get("iron_mg"))
    if iron_pct is not None and iron_pct < 80:
        notes.append(
            f"Iron is at {iron_pct:.0f}% of the daily RDA. Add an iron-rich food "
            "(spinach, a jaggery-based sweet, or egg) with a vitamin-C source to improve absorption."
        )
    fiber_pct = _pct(day.fiber_g, values.get("fiber_g"))
    if fiber_pct is not None and fiber_pct < 80:
        notes.append(
            f"Dietary fibre is at {fiber_pct:.0f}% of the adequate intake; whole grains, "
            "pulses and vegetables with the skin on will close the gap."
        )
    # Vitamin D is the one RDA an Indian plate cannot close: IFCT's only real
    # sources are oily fish, egg yolk, dairy and UV-exposed mushrooms. Say that
    # rather than letting a red 20% look like a failure of the plan.
    vitd_pct = _pct(day.vitamin_d_ug, values.get("vitamin_d_ug"))
    if vitd_pct is not None and vitd_pct < 60:
        notes.append(
            f"Vitamin D is at {vitd_pct:.0f}% of the RDA. Indian foods are weak sources "
            "apart from oily fish, egg yolk and UV-exposed mushrooms, so the rest has to "
            "come from sunlight or fortified milk rather than from more of this plate."
        )
    if day.sodium_mg > 0 and day.sodium_mg > 0.9 * 2000:
        notes.append(
            "Sodium is high. Cut back on pickles, papad and packaged snacks to stay "
            "within the ICMR-NIN 2020 salt guidance (≤5 g/day)."
        )
    if lab_report is not None:
        for finding in lab_report.findings:
            notes.append(f"{finding.label} {finding.status}: {finding.message}")
    return notes


def _pct(actual: float, target: float | None) -> float | None:
    if not target:
        return None
    return 100.0 * actual / target


def generate_meal_plan(
    profile: PlannerProfile,
    *,
    db: FoodDB | None = None,
    seed: int = 42,
) -> MealPlan:
    """Build a day's Indian meal plan for ``profile``."""
    started = time.perf_counter()
    db = db or get_indian_food_db()
    rng = random.Random(seed)

    life_stage = life_stage_for_age(profile.age_years)
    cfg = load_life_stage_config(life_stage)
    sex = profile.sex
    values = daily_values(life_stage, sex)
    thresholds = daily_targets(life_stage, sex)

    # Activity shifts energy (and, proportionally, the ceilings derived from it).
    activity_factor = _ACTIVITY_FACTOR[profile.activity]
    base_energy = energy_target(life_stage, sex) * activity_factor

    lab_report = analyze_lab_text(profile.lab_text, sex=sex) if profile.lab_text else None

    preference, avoid = _preferences(profile, life_stage, lab_report)
    exclude_tags = set(profile.exclude_tags)
    warnings: list[str] = []

    if profile.goal == "weight_management":
        goal_factor = 0.85
    else:
        goal_factor = 1.0
    day_energy_target = base_energy * goal_factor

    meals: list[PlannedMeal] = []
    glycemic_total = 0.0
    #: Dishes already used today, shared across the four meal builders so the day
    #: does not repeat itself.
    day_used: set[str] = set()
    #: The thresholds each slot was actually scored against, so a meal rebuilt
    #: later is scored by exactly the same rules.
    slot_thresholds_by_slot: dict[str, dict[str, Threshold]] = {}
    for slot in MEAL_SLOTS:
        slot_energy = day_energy_target * SLOT_ENERGY_SHARE[slot]
        slot_thresholds = slot_targets(life_stage, sex, slot)
        slot_thresholds_by_slot[slot] = slot_thresholds
        if profile.goal == "weight_management":
            floor = slot_thresholds.get("protein_g")
            if floor and floor.minimum:
                slot_thresholds["protein_g"] = Threshold(
                    minimum=floor.minimum * 1.2, weight=floor.weight
                )
            energy_t = slot_thresholds.get("energy_kcal")
            if energy_t:
                slot_thresholds["energy_kcal"] = Threshold(
                    minimum=(energy_t.minimum or slot_energy) * 0.85,
                    maximum=(energy_t.maximum or slot_energy) * 0.85,
                    weight=energy_t.weight,
                )

        builder = _MealBuilder(
            db,
            slot,
            slot_energy,
            slot_thresholds,
            profile.diet,
            exclude_tags,
            preference,
            avoid,
            rng,
            day_used,
        )
        if slot == "snacks":
            builder.add_snack()
            builder.add_protein()
            builder.add_dairy_serving()
            if slot_energy > _SECOND_SNACK_AT:
                # Never the fruit that was already at breakfast: a second snack
                # that repeats an earlier meal is worse than a smaller snack.
                builder.add_snack(allow_repeat=False)
            if slot_energy > _SECOND_CEREAL_AT[slot]:
                builder.add_staple()
        else:
            builder.add_staple()
            builder.add_protein()
            builder.add_vegetable()
            if slot_energy > _SECOND_CEREAL_AT[slot]:
                builder.add_complementary_cereal(_COMPLEMENT_SHARE[slot])
        builder.rescale_to_energy()

        if not builder.items:
            warnings.append(f"No {profile.diet.replace('_', ' ')} foods were available for {slot}.")
            continue

        nutrients = db.nutrients_for(builder.items)
        added_sugars = estimate_added_sugars(builder.items, db)
        meal_gl = estimate_glycemic_load(builder.items, db)
        glycemic_total += meal_gl
        compliance, _ = _compliance(nutrients, slot_thresholds, added_sugars)
        meals.append(
            PlannedMeal(
                slot=slot,
                title=slot.title(),
                items=[
                    PlanItem(
                        food_id=i.food_id,
                        name=i.name,
                        category=db.get(i.food_id).category,
                        quantity_g=i.quantity_g,
                        form=i.form.value,
                        is_dish=db.get(i.food_id).category == "prepared",
                        nutrients=db.nutrients_for_item(i),
                    )
                    for i in builder.items
                ],
                nutrients=nutrients,
                energy_kcal=round(nutrients.energy_kcal, 1),
                energy_share_of_day=round(SLOT_ENERGY_SHARE[slot], 3),
                macro_shares=_macro_shares(nutrients),
                compliance=round(compliance, 4),
                glycemic_load=round(meal_gl, 2),
                note=" ".join(builder.notes),
            )
        )

    meals = _top_up_cooking_fat(
        meals,
        db,
        fat_band=thresholds.get("share:fat_g"),
        slot_thresholds=slot_thresholds_by_slot,
        day_energy_target=day_energy_target,
        visible_fat_max_g=cfg.guidance_pair("visible_fat_g", (20.0, 35.0))[1],
        oil=_cooking_oil(db, profile.diet, avoid, exclude_tags),
    )

    day = NutrientVector.sum([m.nutrients for m in meals])
    day_added_sugars = sum(
        estimate_added_sugars(
            [
                MealItem(
                    food_id=item.food_id,
                    name=item.name,
                    quantity_g=item.quantity_g,
                    form=Form(item.form),
                )
                for item in m.items
            ],
            db,
        )
        for m in meals
    )
    day_compliance, _ = _compliance(day, thresholds, day_added_sugars)
    day_glycemic_load = round(glycemic_total, 2)

    nutrient_table = _nutrient_table(day, thresholds, day_energy_target)
    insights = _insights(profile, life_stage, values, day, lab_report)
    warnings.append(
        "Sodium and added-sugar figures exclude salt and sugar added during "
        "cooking, which IFCT 2017 does not measure."
    )

    return MealPlan(
        profile=profile,
        life_stage=life_stage,
        life_stage_label=cfg.label,
        sex=sex,
        reference_weight_kg=reference_weight_kg(life_stage),
        source=daily_source(life_stage),
        energy_target_kcal=round(day_energy_target, 1),
        meals=meals,
        day_nutrients=day,
        day_macro_shares=_macro_shares(day),
        day_glycemic_load=day_glycemic_load,
        day_compliance=round(day_compliance, 4),
        nutrient_table=nutrient_table,
        insights=insights,
        warnings=warnings,
        lab_report=lab_report,
        seed=seed,
        runtime_s=round(time.perf_counter() - started, 4),
    )


def _nutrient_table(
    day: NutrientVector,
    thresholds: dict[str, Threshold],
    energy_target_kcal: float,
) -> list[NutrientStatus]:
    """Actual-vs-target rows for the nutrient panel and the charts.

    Carbohydrate and fat have no absolute RDA floor; their targets are the
    midpoint of the AMDR-style energy-share band the life stage carries, turned
    into grams. That is what makes the proportion requirement displayable.

    Band rows also carry the range itself (``band_low``/``band_high``), because a
    plan at either end of a band is as correct as one at its middle -- the
    dashboard judges those rows by membership, not by distance to a midpoint that
    was never a goal.
    """
    rows: list[NutrientStatus] = []
    share_bands = {
        "carbohydrate_g": thresholds.get("share:carbohydrate_g"),
        "fat_g": thresholds.get("share:fat_g"),
    }
    for key in DISPLAY_ORDER:
        label, unit = NUTRIENT_LABELS.get(key, (key, ""))
        threshold = thresholds.get(key)
        actual = float(getattr(day, key, 0.0))
        target: float | None = None
        kind: Literal["floor", "ceiling", "band"] = "floor"
        band = share_bands.get(key)
        band_bounds: tuple[float, float] | None = None
        if threshold is None and band is not None and band.minimum and band.maximum:
            midpoint = (band.minimum + band.maximum) / 2.0
            kcal_per_g = 4.0 if key == "carbohydrate_g" else 9.0
            target = round(energy_target_kcal * midpoint / kcal_per_g, 1)
            band_bounds = (
                round(energy_target_kcal * band.minimum / kcal_per_g, 1),
                round(energy_target_kcal * band.maximum / kcal_per_g, 1),
            )
            kind = "band"
        elif threshold is not None:
            if threshold.minimum is not None and threshold.maximum is not None:
                # Energy is the other band: everything between 0.9x and 1.15x the
                # reference is acceptable, so the midpoint is what a coverage bar
                # can be drawn against and the bounds are what is judged.
                band_bounds = (threshold.minimum, threshold.maximum)
                target = (threshold.minimum + threshold.maximum) / 2.0
                kind = "band"
            elif threshold.maximum is not None:
                target = threshold.maximum
                kind = "ceiling"
            else:
                target = threshold.minimum
                kind = "floor"
        pct = _pct(actual, target)
        rows.append(
            NutrientStatus(
                key=key,
                label=label,
                unit=unit,
                target=None if target is None else round(target, 1),
                actual=round(actual, 1),
                pct=None if pct is None else round(pct, 1),
                kind=kind,
                band_low=None if band_bounds is None else band_bounds[0],
                band_high=None if band_bounds is None else band_bounds[1],
            )
        )
    return rows


def get_food_alternatives(
    slot: str,
    diet: DietType = "vegetarian",
    current_food_id: str | None = None,
    exclude_tags: list[str] | None = None,
    allergies: list[str] | None = None,
    db: FoodDB | None = None,
    limit: int = 30,
) -> list[dict[str, object]]:
    """Return appropriate Indian food alternatives for a given meal slot and diet."""
    db = db or get_indian_food_db()
    compatible = _DIET_COMPATIBLE.get(diet, _DIET_COMPATIBLE["vegetarian"])
    avoid_set = {x.lower().strip() for x in (exclude_tags or []) + (allergies or []) if x}

    slot_pools: list[str] = []
    if slot in _STAPLES:
        slot_pools.extend(_STAPLES[slot])
    if slot in _PROTEINS:
        slot_pools.extend(_PROTEINS[slot])
    if slot in _VEGETABLES:
        slot_pools.extend(_VEGETABLES[slot])

    from foodsense.data.indian_dishes import DISHES

    for dish in DISHES:
        if slot in dish.slots and dish.code not in slot_pools:
            slot_pools.append(dish.code)

    for rec in db.records:
        if f"meal_{slot}" in rec.tags and rec.fdc_id not in slot_pools:
            slot_pools.append(rec.fdc_id)

    results: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for food_id in slot_pools:
        if current_food_id and food_id == current_food_id:
            continue
        if food_id in seen_ids:
            continue
        rec = db.find(food_id)
        if rec is None:
            continue

        if rec.category == "prepared":
            dish_diet = next(
                (t.removeprefix("diet_") for t in rec.tags if t.startswith("diet_")),
                "vegetarian",
            )
            if dish_diet not in compatible:
                continue
        else:
            if not any(f"diet_{d}" in rec.tags for d in compatible):
                continue

        name_lower = rec.name.lower()
        if any(av in rec.tags or av in name_lower for av in avoid_set):
            continue

        std_serving = 100.0
        if rec.category == "prepared":
            d_obj = next((d for d in DISHES if d.code == rec.fdc_id), None)
            if d_obj:
                std_serving = d_obj.serving_g
        elif rec.category == "dairy":
            std_serving = 150.0
        elif rec.category == "fruit":
            std_serving = 120.0
        elif rec.category == "nut_seed":
            std_serving = 25.0

        nutr_100g = rec.nutrients_per_100g
        scale = std_serving / 100.0
        seen_ids.add(food_id)
        results.append(
            {
                "food_id": rec.fdc_id,
                "name": rec.name,
                "category": rec.category,
                "is_dish": rec.category == "prepared",
                "standard_serving_g": round(std_serving, 1),
                "energy_kcal": round(nutr_100g.energy_kcal * scale, 1),
                "protein_g": round(nutr_100g.protein_g * scale, 1),
                "carbohydrate_g": round(nutr_100g.carbohydrate_g * scale, 1),
                "fat_g": round(nutr_100g.fat_g * scale, 1),
                "fiber_g": round(nutr_100g.fiber_g * scale, 1),
                "tags": list(rec.tags),
            }
        )
        if len(results) >= limit:
            break

    return results


def recalculate_meal_plan(
    profile: PlannerProfile,
    meals_data: list[dict[str, object]],
    *,
    db: FoodDB | None = None,
    seed: int = 42,
) -> MealPlan:
    """Recalculate verified nutrition for updated meals, items, or serving sizes."""
    started = time.perf_counter()
    db = db or get_indian_food_db()

    life_stage = life_stage_for_age(profile.age_years)
    cfg = load_life_stage_config(life_stage)
    sex = profile.sex
    values = daily_values(life_stage, sex)
    thresholds = daily_targets(life_stage, sex)

    activity_factor = _ACTIVITY_FACTOR[profile.activity]
    base_energy = energy_target(life_stage, sex) * activity_factor
    goal_factor = 0.85 if profile.goal == "weight_management" else 1.0
    day_energy_target = base_energy * goal_factor

    lab_report = analyze_lab_text(profile.lab_text, sex=sex) if profile.lab_text else None

    meals: list[PlannedMeal] = []
    meal_items_all: list[PlanItem] = []

    for meal_dict in meals_data:
        slot = str(meal_dict.get("slot", "lunch"))
        title = str(meal_dict.get("title", slot.capitalize()))
        raw_items = meal_dict.get("items", []) or []

        plan_items: list[PlanItem] = []
        for item_dict in raw_items:  # type: ignore[union-attr]
            if not isinstance(item_dict, dict):
                continue
            food_id = str(item_dict.get("food_id", ""))
            rec = db.find(food_id)
            if rec is None:
                continue
            grams = float(item_dict.get("quantity_g", 100.0))
            grams = max(5.0, grams)
            form_val = item_dict.get("form")
            if form_val:
                form = str(form_val)
            else:
                form = rec.default_form.value if hasattr(rec.default_form, "value") else str(rec.default_form)
            factor = grams / 100.0
            item_nutrients = rec.nutrients_per_100g.scaled(factor)
            p_item = PlanItem(
                food_id=rec.fdc_id,
                name=rec.name,
                category=rec.category,
                quantity_g=round(grams, 1),
                form=form,
                is_dish=rec.category == "prepared",
                nutrients=item_nutrients,
            )
            plan_items.append(p_item)
            meal_items_all.append(p_item)

        typed_meal_items = [
            MealItem(food_id=pi.food_id, name=pi.name, quantity_g=pi.quantity_g, form=Form(pi.form))
            for pi in plan_items
        ]
        meal_nutrients = db.nutrients_for(typed_meal_items) if typed_meal_items else NutrientVector()

        meal_energy = meal_nutrients.energy_kcal
        macro_shares = _macro_shares(meal_nutrients)
        slot_thresholds = slot_targets(life_stage, sex, slot)
        added_sugars = estimate_added_sugars(typed_meal_items, db) if typed_meal_items else 0.0
        compliance, _ = _compliance(meal_nutrients, slot_thresholds, added_sugars)
        glycemic_load = estimate_glycemic_load(typed_meal_items, db) if typed_meal_items else 0.0

        meals.append(
            PlannedMeal(
                slot=slot,
                title=title,
                items=plan_items,
                nutrients=meal_nutrients,
                energy_kcal=round(meal_energy, 1),
                energy_share_of_day=round(SLOT_ENERGY_SHARE.get(slot, 0.25), 4),
                macro_shares=macro_shares,
                compliance=round(compliance, 4),
                glycemic_load=round(glycemic_load, 1),
                note=str(meal_dict.get("note", "")),
            )
        )

    all_typed_items = [
        MealItem(food_id=pi.food_id, name=pi.name, quantity_g=pi.quantity_g, form=Form(pi.form))
        for pi in meal_items_all
    ]
    day_nutrients = db.nutrients_for(all_typed_items) if all_typed_items else NutrientVector()

    if day_nutrients.energy_kcal > 0:
        for m in meals:
            m.energy_share_of_day = round(m.energy_kcal / day_nutrients.energy_kcal, 4)

    day_macro = _macro_shares(day_nutrients)
    day_glycemic = sum(m.glycemic_load for m in meals)
    day_added_sugars = estimate_added_sugars(all_typed_items, db) if all_typed_items else 0.0
    day_comp, _ = _compliance(day_nutrients, thresholds, day_added_sugars)
    nut_table = _nutrient_table(day_nutrients, thresholds, day_energy_target)
    insights = _insights(profile, life_stage, values, day_nutrients, lab_report)

    return MealPlan(
        profile=profile,
        life_stage=life_stage,
        life_stage_label=cfg.label,
        sex=sex,
        reference_weight_kg=cfg.reference_weight_kg,
        source=cfg.source,
        energy_target_kcal=round(day_energy_target, 1),
        meals=meals,
        day_nutrients=day_nutrients,
        day_macro_shares=day_macro,
        day_glycemic_load=round(day_glycemic, 1),
        day_compliance=round(day_comp, 4),
        nutrient_table=nut_table,
        insights=insights,
        warnings=[],
        lab_report=lab_report,
        seed=seed,
        runtime_s=round(time.perf_counter() - started, 4),
    )
