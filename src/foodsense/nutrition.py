"""Age- and sex-specific nutrient targets for ages 5-20 (ICMR-NIN 2020).

The four-stage counterfactual pipeline has its own ``AgeGroup`` bands and its own
rule engine. This module is the requirement model the Indian *meal planner* is
built on, kept deliberately separate so it can follow the ICMR-NIN 2020 RDA
table directly:

* Each :class:`LifeStage` is one of the ICMR-NIN age bands (4-6, 7-9, 10-12,
  13-15, 16-18, adults), with its published energy, protein, fibre and
  micronutrient reference intakes in ``configs/life_stages/<stage>.yaml``.
* :class:`Sex` selects the boys'/girls' or men's/women's column where the two
  differ. Iron is the largest difference: from 10-12 y the girls' RDA is 28 mg
  against the boys' 16 mg.

Everything is expressed with the same soft :class:`~foodsense.constraints.goals.Threshold`
machinery the rest of the project uses, so a target can be scored smoothly and
compared against a threshold hard.

A daily target is turned into per-meal targets by the planner, which splits the
day across breakfast / lunch / dinner / snacks by energy share rather than
evenly -- a snack is not a third of a dinner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

import yaml

from foodsense import CONFIG_DIR
from foodsense.constraints.goals import Threshold
from foodsense.schemas import LifeStage, Sex

__all__ = [
    "MEAL_SLOTS",
    "SLOT_ENERGY_SHARE",
    "LifeStageConfig",
    "calculate_body_metrics",
    "daily_source",
    "daily_targets",
    "daily_values",
    "energy_target",
    "life_stage_for_age",
    "load_life_stage_config",
    "reference_weight_kg",
    "slot_targets",
]

LIFE_STAGE_DIR = CONFIG_DIR / "life_stages"

#: The four meal categories the plan is divided into, in eating order.
MEAL_SLOTS: tuple[str, ...] = ("breakfast", "lunch", "dinner", "snacks")

#: Fraction of the day's energy each slot is expected to carry. These are the
#: conventional Indian meal-energy split (breakfast ~25%, the two main meals ~30%
#: each, snacks ~15%) and sum to 1.0. Nutrient floors are shared out by the same
#: fractions, so a meal is judged against the share of the day it represents.
SLOT_ENERGY_SHARE: dict[str, float] = {
    "breakfast": 0.25,
    "lunch": 0.30,
    "dinner": 0.30,
    "snacks": 0.15,
}

#: Nutrients measured as a per-day *floor* (raise toward), with the weight each
#: carries in the planner's compliance score. Weights reflect how central a
#: nutrient is in this age range: iron and protein lead.
_FLOORS: dict[str, float] = {
    "protein_g": 1.2,
    "fiber_g": 1.0,
    "calcium_mg": 1.1,
    "iron_mg": 1.3,
    "zinc_mg": 0.6,
    "magnesium_mg": 0.4,
    "vitamin_c_mg": 0.6,
    "vitamin_a_rae_ug": 0.5,
    "folate_dfe_ug": 0.5,
    "vitamin_d_ug": 0.3,
}

#: Potassium floor weight (its minimum comes from ``guidance``, not ``daily``).
_POTASSIUM_WEIGHT = 0.5

#: Nutrients measured as a per-day *ceiling* (keep below): the guidance-derived
#: upper bounds. ``added_sugars_g`` and ``saturated_fat_g`` are implied by the
#: energy-share guidance and computed in :func:`daily_targets`.
_CEILINGS: dict[str, float] = {
    "sodium_mg": 1.2,
    "added_sugars_g": 0.9,
    "saturated_fat_g": 0.8,
}

#: Fraction of a per-meal proportional floor a single meal is expected to supply.
#: Same reasoning as the legacy configs: micronutrient adequacy is a daily
#: question, and demanding the full share at every meal rejects every real meal.
FLOOR_ATTAINMENT = 0.75

#: Kcal per gram of the macronutrients (Atwater).
_ATWATER = {"protein_g": 4.0, "carbohydrate_g": 4.0, "fat_g": 9.0}


@dataclass(frozen=True, slots=True)
class LifeStageConfig:
    """One file from ``configs/life_stages/``."""

    life_stage: LifeStage
    label: str
    age_range: tuple[int, int]
    meals_per_day: float
    source: str
    reference_weight_kg: float
    daily: dict[str, float]
    sex_daily: dict[str, dict[str, float]]
    guidance: dict[str, object] = field(default_factory=dict)

    def resolved(self, sex: Sex | None) -> dict[str, float]:
        """Daily reference intakes for this life stage and sex.

        ``sex=None`` returns the sex-neutral base values (the young bands have no
        sex split at all; the older ones fall back to the common column).
        """
        values = dict(self.daily)
        if sex is not None:
            values.update(self.sex_daily.get(Sex(sex).value, {}))
        return values

    def guidance_pair(self, key: str, default: tuple[float, float]) -> tuple[float, float]:
        raw = self.guidance.get(key, default)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            return float(raw[0]), float(raw[1])
        return default

    def guidance_float(self, key: str, default: float) -> float:
        raw = self.guidance.get(key, default)
        return float(raw) if isinstance(raw, (int, float)) else default


@cache
def load_life_stage_config(life_stage: LifeStage) -> LifeStageConfig:
    """Load and cache ``configs/life_stages/<life_stage>.yaml``."""
    path = LIFE_STAGE_DIR / f"{LifeStage(life_stage).value}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No life-stage configuration at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    age = raw.get("age_range") or [0, 0]
    sex_daily = {
        "male": {k: float(v) for k, v in (raw.get("sex_daily", {}).get("male") or {}).items()},
        "female": {k: float(v) for k, v in (raw.get("sex_daily", {}).get("female") or {}).items()},
    }
    return LifeStageConfig(
        life_stage=LifeStage(raw["life_stage"]),
        label=raw.get("label", raw["life_stage"]),
        age_range=(int(age[0]), int(age[1])),
        meals_per_day=float(raw.get("meals_per_day", 4.0)),
        source=str(raw.get("source", "")),
        reference_weight_kg=float(raw.get("reference_weight_kg", 0.0)),
        daily={k: float(v) for k, v in (raw.get("daily") or {}).items()},
        sex_daily=sex_daily,
        guidance=dict(raw.get("guidance") or {}),
    )


def life_stage_for_age(age_years: int | float) -> LifeStage:
    """Pick the ICMR-NIN band that contains ``age_years`` (within 5-20)."""
    age = int(round(age_years))
    if age < 5 or age > 20:
        raise ValueError("The meal planner supports ages 5-20 years.")
    if age <= 6:
        return LifeStage.CHILD_5_6
    if age <= 9:
        return LifeStage.CHILD_7_9
    if age <= 12:
        return LifeStage.PRETEEN_10_12
    if age <= 15:
        return LifeStage.TEEN_13_15
    if age <= 18:
        return LifeStage.TEEN_16_18
    return LifeStage.YOUNG_ADULT_19_20


def calculate_body_metrics(
    age_years: int,
    sex: Sex | str,
    height_cm: float | None = None,
    weight_kg: float | None = None,
) -> dict[str, object]:
    """Calculate BMI, BMR, and nutritional assessment metrics according to ICMR-NIN 2020."""
    sex_enum = Sex(sex) if isinstance(sex, str) else sex
    life_stage = life_stage_for_age(age_years)
    ref_weight = reference_weight_kg(life_stage)
    base_energy = energy_target(life_stage, sex_enum)

    bmi: float | None = None
    bmi_category: str | None = None
    if height_cm and weight_kg and height_cm > 0:
        height_m = height_cm / 100.0
        bmi = round(weight_kg / (height_m**2), 1)
        # Indian pediatric / youth BMI reference cutoffs
        if age_years < 18:
            if bmi < 14.5:
                bmi_category = "Underweight (<5th percentile)"
            elif bmi < 21.0:
                bmi_category = "Healthy weight (5th–85th percentile)"
            elif bmi < 24.0:
                bmi_category = "Overweight risk (85th–95th percentile)"
            else:
                bmi_category = "High BMI (>95th percentile)"
        else:
            if bmi < 18.5:
                bmi_category = "Underweight (<18.5)"
            elif bmi < 23.0:  # Asian-Indian cutoff
                bmi_category = "Normal (18.5–22.9, Asian-Indian standard)"
            elif bmi < 25.0:
                bmi_category = "Overweight (23.0–24.9)"
            else:
                bmi_category = "Obese (≥25.0)"

    # ICMR-NIN 2020 BMR equations
    w = weight_kg if weight_kg is not None else ref_weight
    if age_years <= 10:
        bmr_kcal = round(22.7 * w + 495 if sex_enum is Sex.MALE else 22.5 * w + 499, 1)
    elif age_years <= 18:
        bmr_kcal = round(17.5 * w + 651 if sex_enum is Sex.MALE else 12.2 * w + 746, 1)
    else:
        bmr_kcal = round(15.3 * w + 679 if sex_enum is Sex.MALE else 14.7 * w + 496, 1)

    return {
        "age_years": age_years,
        "sex": sex_enum.value,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "reference_weight_kg": ref_weight,
        "bmi": bmi,
        "bmi_category": bmi_category,
        "estimated_bmr_kcal": bmr_kcal,
        "base_energy_target_kcal": base_energy,
    }


def reference_weight_kg(life_stage: LifeStage) -> float:
    return load_life_stage_config(life_stage).reference_weight_kg


def daily_values(life_stage: LifeStage, sex: Sex | None) -> dict[str, float]:
    """Resolved daily reference intakes for a life stage and sex."""
    return load_life_stage_config(life_stage).resolved(sex)


def daily_source(life_stage: LifeStage) -> str:
    return load_life_stage_config(life_stage).source


def energy_target(life_stage: LifeStage, sex: Sex | None) -> float:
    return load_life_stage_config(life_stage).resolved(sex).get("energy_kcal", 0.0)


def daily_targets(life_stage: LifeStage, sex: Sex | None) -> dict[str, Threshold]:
    """Every daily target as a :class:`Threshold`, keyed by FoodSense nutrient name.

    Floors come from the RDA table; ceilings for added sugars and saturated fat
    are the ICMR 10%-of-energy limits; energy is a band around the reference.
    """
    cfg = load_life_stage_config(life_stage)
    values = cfg.resolved(sex)
    energy = values.get("energy_kcal", 0.0)

    thresholds: dict[str, Threshold] = {
        "energy_kcal": Threshold(minimum=round(0.9 * energy), maximum=round(1.15 * energy), weight=1.0)
    }
    for nutrient, weight in _FLOORS.items():
        value = values.get(nutrient)
        if value:
            thresholds[nutrient] = Threshold(minimum=float(value), weight=weight)

    # Potassium's adequate intake lives under `guidance`, not `daily`, because it
    # is a WHO/ICMR population AI rather than a per-group RDA.
    thresholds["potassium_mg"] = Threshold(
        minimum=cfg.guidance_float("potassium_ai_mg", 3500.0), weight=_POTASSIUM_WEIGHT
    )

    # Ceilings.
    thresholds["added_sugars_g"] = Threshold(
        maximum=round(energy * cfg.guidance_float("added_sugars_max_energy_share", 0.10) / 4.0, 1),
        weight=_CEILINGS["added_sugars_g"],
    )
    thresholds["saturated_fat_g"] = Threshold(
        maximum=round(
            energy * cfg.guidance_float("saturated_fat_max_energy_share", 0.10) / 9.0, 1
        ),
        weight=_CEILINGS["saturated_fat_g"],
    )
    thresholds["sodium_mg"] = Threshold(
        maximum=float(cfg.guidance_float("sodium_ai_mg", 2000.0) + 500.0),  # AI + tolerance
        weight=_CEILINGS["sodium_mg"],
    )

    # Macro energy-share band (a proportion, not an amount).
    lo, hi = cfg.guidance_pair("total_fat_energy_share", (0.20, 0.35))
    thresholds["share:fat_g"] = Threshold(minimum=lo, maximum=hi, weight=1.0)
    thresholds["share:protein_g"] = Threshold(minimum=0.12, maximum=0.30, weight=1.0)
    thresholds["share:carbohydrate_g"] = Threshold(minimum=0.45, maximum=0.65, weight=1.0)
    return thresholds


def slot_targets(
    life_stage: LifeStage, sex: Sex | None, slot: str
) -> dict[str, Threshold]:
    """Per-meal targets for one slot: each daily target scaled by its energy share.

    Ceilings scale with the share (a sodium ceiling really is per-meal); floors
    scale with the share and then by :data:`FLOOR_ATTAINMENT`, because daily
    adequacy should not be demanded of every individual meal.
    """
    if slot not in SLOT_ENERGY_SHARE:
        raise ValueError(f"Unknown meal slot {slot!r}; expected one of {MEAL_SLOTS}")
    share = SLOT_ENERGY_SHARE[slot]
    out: dict[str, Threshold] = {}
    for key, threshold in daily_targets(life_stage, sex).items():
        if key.startswith("share:"):
            out[key] = threshold  # a share is a share, at any meal
        else:
            out[key] = threshold.scaled(share, FLOOR_ATTAINMENT)
    return out
