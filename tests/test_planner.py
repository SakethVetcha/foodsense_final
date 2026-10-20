"""Tests for the age/sex nutrition targets and the Indian meal planner."""

from __future__ import annotations

import pytest

from foodsense import INDIA_FOOD_DB_PARQUET
from foodsense.nutrition import (
    MEAL_SLOTS,
    daily_values,
    energy_target,
    life_stage_for_age,
    load_life_stage_config,
    slot_targets,
)
from foodsense.planner import PlannerProfile, generate_meal_plan
from foodsense.schemas import LifeStage, Sex

pytestmark = pytest.mark.skipif(
    not INDIA_FOOD_DB_PARQUET.exists(),
    reason="Indian food database not built; run `python -m foodsense.data.build_indian_food_db`",
)


# ---------------------------------------------------------------------------
# Nutrition model
# ---------------------------------------------------------------------------


class TestLifeStages:
    def test_every_stage_loads_and_covers_its_age_range(self):
        for stage in LifeStage:
            cfg = load_life_stage_config(stage)
            low, high = cfg.age_range
            assert low <= high
            assert energy_target(stage, Sex.MALE) > 0

    def test_age_maps_to_the_icmr_band(self):
        assert life_stage_for_age(5) is LifeStage.CHILD_5_6
        assert life_stage_for_age(9) is LifeStage.CHILD_7_9
        assert life_stage_for_age(12) is LifeStage.PRETEEN_10_12
        assert life_stage_for_age(15) is LifeStage.TEEN_13_15
        assert life_stage_for_age(18) is LifeStage.TEEN_16_18
        assert life_stage_for_age(20) is LifeStage.YOUNG_ADULT_19_20

    def test_below_five_years_is_rejected(self):
        with pytest.raises(ValueError):
            life_stage_for_age(4)

    def test_icmr_energy_values_are_reproduced(self):
        """Published Table 1a energies, hard-coded here as the contract."""
        assert energy_target(LifeStage.CHILD_7_9, Sex.MALE) == 1700
        assert energy_target(LifeStage.PRETEEN_10_12, Sex.MALE) == 2220
        assert energy_target(LifeStage.PRETEEN_10_12, Sex.FEMALE) == 2060
        assert energy_target(LifeStage.TEEN_13_15, Sex.MALE) == 2860
        assert energy_target(LifeStage.TEEN_16_18, Sex.FEMALE) == 2500

    def test_girls_need_far_more_iron_than_boys_in_adolescence(self):
        """The single clearest reason sex has to be an input."""
        for stage in (LifeStage.PRETEEN_10_12, LifeStage.TEEN_13_15, LifeStage.TEEN_16_18):
            female = daily_values(stage, Sex.FEMALE)["iron_mg"]
            male = daily_values(stage, Sex.MALE)["iron_mg"]
            assert female > male

    def test_slot_targets_scale_with_the_slot_share(self):
        lunch = slot_targets(LifeStage.TEEN_13_15, Sex.MALE, "lunch")
        snacks = slot_targets(LifeStage.TEEN_13_15, Sex.MALE, "snacks")
        assert (lunch["protein_g"].minimum or 0) > (snacks["protein_g"].minimum or 0)
        assert MEAL_SLOTS == ("breakfast", "lunch", "dinner", "snacks")


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class TestPlanner:
    def test_produces_all_four_meal_categories(self):
        plan = generate_meal_plan(PlannerProfile(age_years=12, sex="female"))
        assert [m.slot for m in plan.meals] == ["breakfast", "lunch", "dinner", "snacks"]
        assert all(m.items for m in plan.meals)

    def test_every_age_and_sex_is_plannable(self):
        for age in (5, 8, 11, 14, 17, 20):
            for sex in ("male", "female"):
                plan = generate_meal_plan(PlannerProfile(age_years=age, sex=sex), seed=1)
                assert len(plan.meals) == 4
                assert plan.day_nutrients.energy_kcal > 0

    def test_is_deterministic_under_a_seed(self):
        profile = PlannerProfile(age_years=14, sex="female")
        a = generate_meal_plan(profile, seed=99)
        b = generate_meal_plan(profile, seed=99)
        assert [i.food_id for m in a.meals for i in m.items] == [
            i.food_id for m in b.meals for i in m.items
        ]

    def test_a_different_seed_can_change_the_plan(self):
        profile = PlannerProfile(age_years=14, sex="female")
        a = generate_meal_plan(profile, seed=1)
        b = generate_meal_plan(profile, seed=2)
        assert [i.food_id for m in a.meals for i in m.items] != [
            i.food_id for m in b.meals for i in m.items
        ]

    def test_energy_lands_near_the_target(self):
        plan = generate_meal_plan(PlannerProfile(age_years=13, sex="female"), seed=4)
        ratio = plan.day_nutrients.energy_kcal / plan.energy_target_kcal
        assert 0.8 <= ratio <= 1.1

    @pytest.mark.parametrize("activity", ["sedentary", "moderate", "heavy"])
    def test_energy_lands_near_the_target_at_every_activity_level(self, activity):
        """A 15-year-old boy on heavy work needs ~3300 kcal. One bowl cannot carry
        that alone; the plate has to grow a dish, not a portion."""
        plan = generate_meal_plan(
            PlannerProfile(age_years=16, sex="male", activity=activity), seed=7
        )
        ratio = plan.day_nutrients.energy_kcal / plan.energy_target_kcal
        assert 0.85 <= ratio <= 1.05

    def test_a_large_slot_pairs_two_cereal_groups(self):
        """Roti *and* rice, not a single 400 g bowl of khichdi."""
        plan = generate_meal_plan(
            PlannerProfile(age_years=16, sex="male", activity="heavy"), seed=7
        )
        lunch = next(m for m in plan.meals if m.slot == "lunch")
        assert len(lunch.items) >= 4
        # No single item may carry the whole slot either.
        assert all(item.quantity_g < 400 for item in lunch.items)

    def test_the_day_does_not_repeat_a_dish(self):
        """The same sabzi at lunch and dinner is a bug in a demo, not in a diet."""
        plan = generate_meal_plan(
            PlannerProfile(age_years=16, sex="male", activity="heavy", diet="non_vegetarian"),
            seed=7,
        )
        # Cooking oil is the same bottle all day and is deliberately excluded --
        # the point is that no *dish* is served twice.
        ids = [
            item.food_id
            for meal in plan.meals
            for item in meal.items
            if item.category != "fat_oil"
        ]
        assert len(ids) == len(set(ids))

    def test_a_low_fat_vegetarian_day_gains_its_cooking_oil(self):
        """A vegetarian plate built only from IFCT composition reads low on fat.

        IFCT measures the food, not the pan it was cooked in. The plan closes the
        gap with an explicit entry -- capped by the life stage's own visible-fat
        guidance -- rather than by quietly inflating a portion.
        """
        plan = generate_meal_plan(
            PlannerProfile(age_years=11, sex="male", diet="vegetarian"), seed=7
        )
        oil = [
            item
            for meal in plan.meals
            for item in meal.items
            if item.category == "fat_oil"
        ]
        assert oil, "expected the cooking fat to appear on the plate"
        assert all(item.quantity_g >= 5.0 for item in oil)
        assert sum(item.quantity_g for item in oil) <= 35.0  # the 10-12 y guidance cap
        assert 0.20 <= plan.day_macro_shares["fat"] <= 0.35
        assert any("cooking" in meal.note for meal in plan.meals)

    def test_a_day_already_inside_the_fat_band_is_left_alone(self):
        """This mix of dishes reaches the band on its own, so nothing is added."""
        plan = generate_meal_plan(
            PlannerProfile(
                age_years=14, sex="female", activity="sedentary", diet="non_vegetarian"
            ),
            seed=7,
        )
        assert all(
            item.category != "fat_oil" for meal in plan.meals for item in meal.items
        )
        assert 0.20 <= plan.day_macro_shares["fat"] <= 0.35

    def test_an_active_teenager_gets_a_real_snack(self):
        plan = generate_meal_plan(
            PlannerProfile(age_years=17, sex="male", activity="heavy"), seed=2
        )
        snacks = next(m for m in plan.meals if m.slot == "snacks")
        assert snacks.energy_kcal > 300

    def test_macronutrient_proportions_are_reported_and_reasonable(self):
        plan = generate_meal_plan(PlannerProfile(age_years=15, sex="male"), seed=5)
        shares = plan.day_macro_shares
        assert set(shares) == {"protein", "carbohydrate", "fat"}
        assert abs(sum(shares.values()) - 1.0) < 0.05
        assert 0.10 <= shares["protein"] <= 0.35

    def test_nutrient_table_covers_the_headline_nutrients(self):
        plan = generate_meal_plan(PlannerProfile(age_years=10, sex="male"), seed=1)
        keys = {row.key for row in plan.nutrient_table}
        for key in ("energy_kcal", "protein_g", "carbohydrate_g", "fat_g", "fiber_g", "iron_mg"):
            assert key in keys
        # Every row has a target so the dashboard can draw an achievement bar.
        assert all(row.target is not None for row in plan.nutrient_table)

    def test_vegetarian_plans_never_contain_meat(self):
        plan = generate_meal_plan(
            PlannerProfile(age_years=13, sex="male", diet="vegetarian"), seed=6
        )
        for meal in plan.meals:
            for item in meal.items:
                assert "diet_vegetarian" in _tags(item)

    def test_gluten_exclusion_removes_wheat_dishes(self):
        plan = generate_meal_plan(
            PlannerProfile(age_years=12, sex="female", exclude_tags=["gluten"]), seed=1
        )
        names = {item.name for meal in plan.meals for item in meal.items}
        assert "Chapati (roti)" not in names
        assert "Aloo paratha" not in names

    def test_adolescent_girls_plan_is_iron_rich(self):
        """The higher RDA should visibly change the food chosen, not just the target."""
        plan = generate_meal_plan(PlannerProfile(age_years=14, sex="female"), seed=3)
        iron = plan.day_nutrients.iron_mg
        rda = daily_values(LifeStage.TEEN_13_15, Sex.FEMALE)["iron_mg"]
        assert iron >= 0.7 * rda

    def test_lab_report_feeds_into_insights(self):
        plan = generate_meal_plan(
            PlannerProfile(
                age_years=16,
                sex="male",
                lab_text="Hemoglobin 10.1 g/dL\nVitamin D 16 ng/mL",
            ),
            seed=1,
        )
        assert plan.lab_report is not None
        assert {f.marker for f in plan.lab_report.findings} == {"hemoglobin", "vitamin_d"}
        assert any("Haemoglobin" in note for note in plan.insights)

    def test_weight_management_targets_less_energy(self):
        base = generate_meal_plan(PlannerProfile(age_years=17, sex="male"), seed=1)
        cut = generate_meal_plan(
            PlannerProfile(age_years=17, sex="male", goal="weight_management"), seed=1
        )
        assert cut.energy_target_kcal < base.energy_target_kcal

    def test_plan_is_verified_by_construction(self):
        plan = generate_meal_plan(PlannerProfile(age_years=9, sex="female"))
        assert plan.verified is True
        assert plan.source.startswith("ICMR-NIN 2020")


def _tags(item):
    from foodsense.data.fdc import get_indian_food_db

    return get_indian_food_db().get(item.food_id).tags
