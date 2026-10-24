"""Integration tests for Indian nutrition data in the Four-Stage Research Pipeline.

Verifies:
1. Unified food catalog (USDA + IFCT 2017 + Composite dishes) with explicit provenance.
2. Search and alias matching for Indian foods (roti, dal, idli, dosa, poha, rajma, paneer).
3. Unit consistency, missing nutrient handling (vitamin B12 unmeasured in IFCT, not zero).
4. Composite dish formulations (constituent ingredient sums match dish record without double counting).
5. Stage 1 OOD detection, source-aware adapter, and confidence notes for Indian foods.
6. Stage 2 availability constraint (only foods from planned meal + pantry are proposed).
7. Stage 3 natural language explanation with data source attribution.
8. Stage 4 source-specific verification (USDA vs IFCT vs Composite ingredient sums).
9. ICMR-NIN 2020 single-meal lunch target scaling.
10. End-to-end execution of Indian research demo scenarios.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from foodsense.api.main import app
from foodsense.constraints.engine import RuleEngine
from foodsense.data.fdc import get_food_db, get_unified_food_db
from foodsense.data.indian_dishes import DISHES
from foodsense.nutrition import LifeStage, Sex, slot_targets
from foodsense.pipeline import run_pipeline, run_scenario
from foodsense.scenarios import (
    ALL_SCENARIOS,
    INDIAN_ADOLESCENT_IRON,
    INDIAN_ADULT_GLYCEMIC,
    INDIAN_TODDLER_SAFETY,
    load_scenario,
)
from foodsense.schemas import (
    AgeGroup,
    Form,
    Goal,
    HealthFlag,
    Meal,
    MealItem,
    NutrientVector,
    UserProfile,
)
from foodsense.stage2_optimizer.de_optimizer import DEConfig
from foodsense.stage2_optimizer.space import build_space
from foodsense.stage3_rag.providers import TemplateProvider
from foodsense.stage3_rag.translate import build_diff, translate
from foodsense.stage4_verification.verifier import verify


@pytest.fixture(scope="module")
def unified_db():
    return get_unified_food_db()


@pytest.fixture(scope="module")
def engine(unified_db):
    return RuleEngine(db=unified_db)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Unified Food Catalog & Provenance
# ---------------------------------------------------------------------------


class TestUnifiedFoodCatalog:
    def test_catalog_contains_usda_and_indian_foods(self, unified_db):
        sources = unified_db.sources()
        assert sources.get("USDA", 0) >= 2500
        assert sources.get("IFCT_2017", 0) >= 500
        assert sources.get("COMPOSITE", 0) >= 30
        assert len(unified_db) > 3100

    def test_zero_id_collision_between_sources(self, unified_db):
        usda_ids = {r.fdc_id for r in unified_db.by_source("USDA")}
        ifct_ids = {r.fdc_id for r in unified_db.by_source("IFCT_2017")}
        comp_ids = {r.fdc_id for r in unified_db.by_source("COMPOSITE")}
        assert not (usda_ids & ifct_ids), "USDA and IFCT food IDs collided"
        assert not (usda_ids & comp_ids), "USDA and Composite food IDs collided"
        assert not (ifct_ids & comp_ids), "IFCT and Composite food IDs collided"

    def test_indian_foods_and_staples_are_searchable(self, unified_db):
        queries = ["roti", "dal", "idli", "dosa", "poha", "rajma", "paneer"]
        for q in queries:
            results = unified_db.search(q, limit=5)
            assert results, f"Query {q!r} returned no search results"
            best_rec, score = results[0]
            assert score >= 70.0, f"Query {q!r} best match {best_rec.name} score too low ({score})"
            assert best_rec.is_indian or best_rec.source in ("IFCT_2017", "COMPOSITE")

    def test_ifct_foods_record_missing_b12_explicitly(self, unified_db):
        ifct_foods = unified_db.by_source("IFCT_2017")
        assert ifct_foods
        for food in ifct_foods[:10]:
            assert "vitamin_b12_ug" in food.missing_nutrients
            assert food.nutrients_per_100g.vitamin_b12_ug == 0.0

    def test_composite_dishes_match_constituent_ingredient_sums(self, unified_db):
        """Dishes must not fabricate nutrients or double-count constituents."""
        for dish in DISHES:
            if not dish.yield_g or not dish.ingredients:
                continue
            rec = unified_db.find(dish.code)
            assert rec is not None, f"Composite dish {dish.code} not found in DB"
            assert rec.is_composite
            assert rec.source == "COMPOSITE"
            assert rec.yield_g == pytest.approx(dish.yield_g)

            # Independently sum constituent nutrients
            ing_vectors = []
            for ing_id, qty in dish.ingredients.items():
                ing_rec = unified_db.find(ing_id)
                assert ing_rec is not None, f"Ingredient {ing_id} for dish {dish.code} not found"
                ing_vectors.append(ing_rec.nutrients_for(qty))

            expected_per_100g = NutrientVector.sum(ing_vectors).scaled(100.0 / dish.yield_g)
            assert rec.nutrients_per_100g.energy_kcal == pytest.approx(
                expected_per_100g.energy_kcal, rel=1e-3
            )
            assert rec.nutrients_per_100g.protein_g == pytest.approx(
                expected_per_100g.protein_g, rel=1e-3
            )


# ---------------------------------------------------------------------------
# 2. Stage 1 — ML Suitability & Out-of-Distribution Handling
# ---------------------------------------------------------------------------


class TestStage1IndianIntegration:
    def test_pure_usda_meal_is_not_ood(self, unified_db):
        profile = UserProfile(age_group=AgeGroup.ADULT, weight_kg=70.0)
        meal = Meal(items=[unified_db.by_source("USDA")[0].as_item(150.0)])
        trace = run_pipeline(profile, meal, db=unified_db)
        assert not trace.stage1.is_ood
        assert trace.stage1.confidence_note is None

    def test_indian_meal_is_flagged_as_ood_with_adapter_note(self, unified_db):
        profile = UserProfile(age_group=AgeGroup.ADULT, weight_kg=60.0)
        # Chapati (X005) + Toor Dal (X031)
        meal = Meal(items=[unified_db.get("X005").as_item(80.0), unified_db.get("X031").as_item(120.0)])
        trace = run_pipeline(profile, meal, db=unified_db)
        assert trace.stage1.is_ood is True
        assert trace.stage1.prediction_source == "source_aware_adapter"
        assert trace.stage1.confidence_note is not None
        assert "Food.com" in trace.stage1.confidence_note
        assert "out-of-distribution" in trace.stage1.confidence_note.lower()
        assert 0.0 <= trace.stage1.suitability <= 1.0


# ---------------------------------------------------------------------------
# 3. Stage 2 — Counterfactual Optimizer & Availability Constraints
# ---------------------------------------------------------------------------


class TestStage2IndianOptimizer:
    def test_space_contains_only_planned_and_pantry_foods(self, unified_db):
        planned = Meal(items=[unified_db.get("X005").as_item(60.0)])
        pantry = Meal(items=[unified_db.get("X031").as_item(0.0), unified_db.get("X047").as_item(0.0)])
        space = build_space(planned, pantry, db=unified_db)
        food_ids = {v.food_id for v in space.variables}
        assert food_ids == {"X005", "X031", "X047"}

    def test_optimizer_never_proposes_unsupplied_indian_foods(self, unified_db):
        profile = UserProfile(
            age_group=AgeGroup.ADULT,
            age_months=14 * 12,
            weight_kg=48.0,
            goal=Goal.BALANCED_NUTRITION,
            health_flags=[HealthFlag.IRON_FOCUS],
            life_stage=LifeStage.TEEN_13_15,
            sex=Sex.FEMALE,
        )
        planned = Meal(items=[unified_db.get("X005").as_item(60.0), unified_db.get("X031").as_item(100.0)])
        pantry = Meal(items=[unified_db.get("X047").as_item(0.0)])  # Only Bajra Roti in pantry

        trace = run_pipeline(profile, planned, pantry, db=unified_db)
        final_ids = trace.final_meal.food_ids()
        allowed_ids = {"X005", "X031", "X047"}
        assert final_ids.issubset(allowed_ids), f"Final meal contains unsupplied foods: {final_ids - allowed_ids}"


# ---------------------------------------------------------------------------
# 4. Stage 3 — Recommendation Generation & Data Source Attribution
# ---------------------------------------------------------------------------


class TestStage3IndianRecommendation:
    def test_diff_records_data_source_provenance(self, unified_db, engine):
        planned = Meal(items=[unified_db.get("X005").as_item(100.0)])
        optimized = Meal(
            items=[unified_db.get("X005").as_item(60.0), unified_db.get("X047").as_item(50.0)]
        )
        diff = build_diff(planned, optimized, [], db=unified_db)
        sources = {c.food_id: c.source for c in diff.changes}
        assert sources.get("X005") == "COMPOSITE"
        assert sources.get("X047") == "COMPOSITE"

    def test_template_provider_includes_source_attribution_and_quantities(self, unified_db, engine):
        profile = UserProfile(age_group=AgeGroup.ADULT, weight_kg=60.0)
        planned = Meal(items=[unified_db.get("X005").as_item(120.0)])
        optimized = Meal(
            items=[unified_db.get("X005").as_item(60.0), unified_db.get("X037").as_item(100.0)]
        )
        result = translate(planned, optimized, profile, db=unified_db, engine=engine)
        text = result.text.lower()
        assert "chapati" in text
        assert "palak paneer" in text
        # Rationale must state data source attribution
        rationale_str = " ".join(result.rationale)
        assert "source" in rationale_str.lower()


# ---------------------------------------------------------------------------
# 5. Stage 4 — Independent Verification
# ---------------------------------------------------------------------------


class TestStage4IndianVerification:
    def test_composite_dish_verified_with_ingredient_sums(self, unified_db, engine):
        item = unified_db.get("X001").as_item(150.0)  # Idli
        profile = UserProfile(age_group=AgeGroup.ADULT, weight_kg=65.0)
        final_meal, report = verify([item], profile, db=unified_db, engine=engine)
        assert report.final_pass
        assert report.sources.get("X001") == "COMPOSITE"
        assert report.source_breakdown.get("COMPOSITE") == 1
        assert any("constituent" in note.lower() for note in report.source_notes)

    def test_ifct_food_verified_against_ifct_catalog_with_b12_note(self, unified_db, engine):
        item = unified_db.get("L003").as_item(100.0)  # Paneer
        profile = UserProfile(age_group=AgeGroup.ADULT, weight_kg=65.0)
        final_meal, report = verify([item], profile, db=unified_db, engine=engine)
        assert report.final_pass
        assert report.sources.get("L003") == "IFCT_2017"
        assert any("vitamin_b12_ug unmeasured" in note for note in report.source_notes)

    def test_unmatched_unverifiable_food_fails_verification(self, unified_db, engine):
        class NullRetriever:
            def ground(self, name):
                return None

        bogus = MealItem(food_id="NONEXISTENT_999", name="Unresolvable Gibberish Food", quantity_g=100.0)
        profile = UserProfile(age_group=AgeGroup.ADULT)
        _, report = verify([bogus], profile, db=unified_db, engine=engine, retriever=NullRetriever())
        assert not report.final_pass
        assert "Unresolvable Gibberish Food" in report.unverifiable

    def test_availability_violation_caught_by_verification(self, unified_db, engine):
        planned = Meal(items=[unified_db.get("X005").as_item(60.0)])
        pantry = Meal(items=[])
        # Generator tried to sneak in Palak Paneer (X037) not in planned or pantry
        unauthorized = [unified_db.get("X005").as_item(60.0), unified_db.get("X037").as_item(100.0)]
        profile = UserProfile(age_group=AgeGroup.ADULT)
        _, report = verify(unauthorized, profile, db=unified_db, engine=engine, planned_meal=planned, pantry=pantry)
        assert not report.final_pass
        assert any(v.rule_id == "verification.availability" for v in report.flagged)


# ---------------------------------------------------------------------------
# 6. ICMR-NIN 2020 Life Stage Targets & Dietary Preferences
# ---------------------------------------------------------------------------


class TestICMRNINTargetsAndDiet:
    def test_icmr_nin_lunch_slot_rules_generated(self, engine):
        profile = UserProfile(
            age_group=AgeGroup.ADULT,
            age_months=14 * 12,
            weight_kg=48.0,
            life_stage=LifeStage.TEEN_13_15,
            sex=Sex.FEMALE,
        )
        rules = engine.rules_for(profile)
        nin_rules = [r for r in rules if r.rule_id.startswith("icmr_nin.teen_13_15")]
        assert len(nin_rules) >= 15
        rule_quantities = {r.quantity for r in nin_rules}
        assert "iron_mg" in rule_quantities
        assert "calcium_mg" in rule_quantities
        assert "energy_kcal" in rule_quantities

    def test_vegetarian_diet_flags_non_vegetarian_dishes(self, unified_db, engine):
        profile = UserProfile(
            age_group=AgeGroup.ADULT,
            diet="vegetarian",
        )
        # Chicken curry (X042) is non-vegetarian
        chicken_curry = unified_db.get("X042").as_item(150.0)
        evaluation = engine.evaluate([chicken_curry], profile)
        assert not evaluation.is_safe
        assert any(v.rule_id == "dietary.vegetarian_exclusion" for v in evaluation.violations)


# ---------------------------------------------------------------------------
# 7. Indian Research Demo Scenarios End-to-End
# ---------------------------------------------------------------------------


class TestIndianScenariosEndToEnd:
    def test_indian_adolescent_iron_scenario(self):
        trace = run_scenario("indian_adolescent_iron")
        assert trace.stage4.final_pass
        assert trace.stage1.is_ood
        assert "COMPOSITE" in trace.stage4.source_breakdown or "IFCT_2017" in trace.stage4.source_breakdown

    def test_indian_adult_glycemic_scenario(self):
        trace = run_scenario("indian_adult_glycemic")
        assert trace.stage4.final_pass
        assert trace.stage1.is_ood
        assert len(trace.stage4.source_breakdown) >= 2  # Cross-dataset

    def test_indian_toddler_safety_scenario(self):
        trace = run_scenario("indian_toddler_safety")
        assert trace.stage4.final_pass
        # Peanuts were in planned meal as whole peanuts; final meal must NOT contain whole peanuts
        for item in trace.final_meal.items:
            if "peanut" in item.name.lower():
                assert item.form != Form.WHOLE


# ---------------------------------------------------------------------------
# 8. API Endpoints: Scenarios, Autocomplete & JSON Trace Export
# ---------------------------------------------------------------------------


class TestAPIExtensions:
    def test_api_foods_returns_indian_foods_and_badges(self, client):
        resp = client.get("/api/foods?q=roti&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        first = data[0]
        assert "source" in first
        assert first["source"] in ("COMPOSITE", "IFCT_2017")
        assert "is_indian" in first

    def test_api_foods_source_filter(self, client):
        resp = client.get("/api/foods?q=rice&source=ifct_2017")
        assert resp.status_code == 200
        for item in resp.json():
            assert item["source"] == "IFCT_2017"

    def test_api_indian_scenarios_endpoint(self, client):
        resp = client.get("/api/indian-scenarios")
        assert resp.status_code == 200
        keys = {s["key"] for s in resp.json()}
        assert keys == {"indian_adolescent_iron", "indian_adult_glycemic", "indian_toddler_safety"}

    def test_api_export_trace_endpoint(self, client):
        resp = client.post("/api/export", json={"scenario": "indian_adolescent_iron"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert "attachment" in resp.headers["content-disposition"]
        trace = resp.json()
        assert trace["scenario"] == "indian_adolescent_iron"
        assert "stage1" in trace and "stage4" in trace
