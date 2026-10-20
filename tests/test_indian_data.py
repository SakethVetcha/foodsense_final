"""Tests for the Indian food database built from IFCT 2017.

These check the *data*, not the plumbing: that the unit conversions are right
against values published in the IFCT 2017 book, that composite dishes are genuine
ingredient sums, and that the tags the planner filters on actually exist.
"""

from __future__ import annotations

import pytest

from foodsense import INDIA_FOOD_DB_PARQUET
from foodsense.data.fdc import get_indian_food_db
from foodsense.data.indian_dishes import DISHES
from foodsense.data.indian_food import curate_indian_food_db, load_ifct_table
from foodsense.schemas import NUTRIENTS

pytestmark = pytest.mark.skipif(
    not INDIA_FOOD_DB_PARQUET.exists(),
    reason="Indian food database not built; run `python -m foodsense.data.build_indian_food_db`",
)


@pytest.fixture(scope="module")
def indian_db():
    return get_indian_food_db()


class TestUnitConversion:
    """Spot-checks against values printed in the published IFCT 2017 tables."""

    def test_rice_raw_milled_matches_published_values(self, indian_db):
        n = indian_db.get("A015").nutrients_per_100g
        # IFCT 2017: 356 kcal, 7.94 g protein, 0.52 g fat, 78.24 g carb, 2.81 g fibre.
        assert n.energy_kcal == pytest.approx(356.4, abs=1.0)
        assert n.protein_g == pytest.approx(7.94, abs=0.05)
        assert n.carbohydrate_g == pytest.approx(78.24, abs=0.05)
        assert n.fiber_g == pytest.approx(2.81, abs=0.05)

    def test_milk_cow_matches_published_values(self, indian_db):
        n = indian_db.get("L002").nutrients_per_100g
        # IFCT 2017: 73 kcal, 3.26 g protein, 4.48 g fat, 118 mg calcium.
        assert n.energy_kcal == pytest.approx(72.9, abs=1.0)
        assert n.protein_g == pytest.approx(3.26, abs=0.05)
        assert n.calcium_mg == pytest.approx(118.0, abs=1.0)

    def test_minerals_are_in_milligrams_not_grams(self, indian_db):
        """A unit slip here would be a 1000x error and would wreck every target."""
        spinach = indian_db.get("C033").nutrients_per_100g
        assert 1.0 < spinach.calcium_mg < 200.0
        assert 1.0 < spinach.iron_mg < 10.0

    def test_energy_is_not_left_in_kilojoules(self, indian_db):
        """Sanity band: no everyday food should read as >1000 kcal per 100 g."""
        offenders = [
            r.name for r in indian_db.records if r.nutrients_per_100g.energy_kcal > 1000
        ]
        assert offenders == []

    def test_vitamin_a_is_retinol_activity_not_a_1to1_carotene_sum(self, indian_db):
        """IFCT sums retinol and carotene 1:1; the RDAs are in RAE, so divide by 12.

        Loading `vita` directly overstated plant vitamin A by an order of
        magnitude -- a vegetarian day read 886% of the RDA on carotene alone.
        """
        spinach = indian_db.get("C033").nutrients_per_100g
        liver = indian_db.get("N005").nutrients_per_100g
        # IFCT prints 2605 ug of carotenoids for spinach; RAE is that / 12.
        assert spinach.vitamin_a_rae_ug == pytest.approx(2605 / 12, rel=0.05)
        # Retinol is already RAE: animal sources must be untouched.
        assert liver.vitamin_a_rae_ug == pytest.approx(3486, rel=0.05)

    def test_vitamin_d_only_comes_from_groups_where_it_is_a_real_source(self, indian_db):
        """The extract's vitd is D2, and reports 109 ug for pomegranate alone.

        One serving would exceed an adolescent's RDA seven times over and the
        tolerable upper intake level twice, so those rows contribute nothing.
        """
        assert indian_db.get("E055").nutrients_per_100g.vitamin_d_ug == 0.0  # pomegranate
        assert indian_db.get("G010").nutrients_per_100g.vitamin_d_ug == 0.0  # curry leaves
        # The plausible sources are kept.
        assert indian_db.get("L002").nutrients_per_100g.vitamin_d_ug == pytest.approx(1.22, rel=0.05)
        assert indian_db.get("J001").nutrients_per_100g.vitamin_d_ug > 5.0  # button mushroom


class TestCompositeDishes:
    def test_every_dish_is_in_the_database(self, indian_db):
        for dish in DISHES:
            record = indian_db.find(dish.code)
            assert record is not None, f"{dish.code} missing"
            assert record.name == dish.name

    def test_dish_nutrients_are_the_ingredient_sum(self, indian_db):
        """Idli = parboiled rice + black gram dal, per 100 g of the served mix."""
        dish = next(d for d in DISHES if d.code == "X001")
        total = 0.0
        for code, grams in dish.ingredients.items():
            total += indian_db.get(code).nutrients_per_100g.energy_kcal * grams / 100.0
        expected_per_100g = total * 100.0 / dish.serving_g
        assert indian_db.get("X001").nutrients_per_100g.energy_kcal == pytest.approx(
            expected_per_100g, rel=0.02
        )

    def test_dishes_carry_meal_slot_tags(self, indian_db):
        for dish in DISHES:
            tags = indian_db.get(dish.code).tags
            for slot in dish.slots:
                assert f"meal_{slot}" in tags

    def test_grain_tags_propagate_from_ingredients(self, indian_db):
        """Chapati is wheat, so a gluten exclusion must remove it."""
        assert "gluten" in indian_db.get("X005").tags
        assert "gluten" not in indian_db.get("X047").tags  # bajra is a millet


class TestCuration:
    def test_all_nutrient_columns_are_present(self, indian_db):
        for record in indian_db.records[:50]:
            for nutrient in NUTRIENTS:
                assert hasattr(record.nutrients_per_100g, nutrient)

    def test_diet_tags_exist_for_every_food(self, indian_db):
        for record in indian_db.records:
            assert any(t.startswith("diet_") for t in record.tags), record.name

    def test_regenerating_is_deterministic(self):
        a, _ = curate_indian_food_db(load_ifct_table())
        b, _ = curate_indian_food_db(load_ifct_table())
        assert a.equals(b)

    def test_no_duplicate_food_ids(self, indian_db):
        ids = [r.fdc_id for r in indian_db.records]
        assert len(ids) == len(set(ids))


class TestSearch:
    def test_finds_a_dish_by_name(self, indian_db):
        names = [r.name for r, _ in indian_db.search("idli", 3)]
        assert "Idli" in names

    def test_finds_a_common_ingredient(self, indian_db):
        names = [r.name for r, _ in indian_db.search("spinach", 3)]
        assert "Spinach" in names
