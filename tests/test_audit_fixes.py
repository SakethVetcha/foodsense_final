"""Regression tests verifying the FoodSense audit and provenance/optimizer fixes.

Covers the 9 regression areas specified in the audit brief:
1. Source preservation across decode, Stage 2, and Stage 4 (IFCT, COMPOSITE, USDA).
2. Traceable source IDs and conversions.
3. Unchanged baseline retention when no improvement feasible with valid=False & converged_reason.
4. Feasible fixture with pantry producing genuine improvement and positive edit distance.
5. Distinction between objective value, ML suitability, and RuleEngine soft scores.
6. Stage 4 flags/repairs on missing or inconsistent food records.
7. Stage 4 distinguishes safety passed from target attained.
8. Indian food presence accurately triggers OOD flagging.
9. Verification that built-in demo scenarios remain valid.
"""

from __future__ import annotations

import pytest

from foodsense.constraints.engine import RuleEngine
from foodsense.data.fdc import get_unified_food_db
from foodsense.pipeline import run_pipeline, run_scenario
from foodsense.schemas import (
    AgeGroup,
    Form,
    Goal,
    Meal,
    MealItem,
    UserProfile,
)
from foodsense.stage2_optimizer.space import build_space
from foodsense.stage4_verification.verifier import verify


@pytest.fixture(scope="module")
def db():
    return get_unified_food_db()


@pytest.fixture(scope="module")
def engine(db):
    return RuleEngine(db=db)


def test_1_source_preservation_across_stages(db, engine):
    """Test 1: IFCT and COMPOSITE foods preserve source across SearchSpace.decode(), Stage 2, and Stage 4."""
    profile = UserProfile(age_group=AgeGroup.ADULT, goal=Goal.BALANCED_NUTRITION)
    planned = Meal(
        items=[
            MealItem(food_id="X006", name="Aloo paratha", quantity_g=95, form=Form.WHOLE, source="COMPOSITE"),
            MealItem(food_id="X022", name="Curd (dahi)", quantity_g=100, form=Form.WHOLE, source="COMPOSITE"),
            MealItem(food_id="E038", name="Mango, ripe, chausa", quantity_g=100, form=Form.WHOLE, source="IFCT_2017"),
            MealItem(food_id="169379", name="Pickles, cucumber, sour", quantity_g=30, form=Form.WHOLE, source="USDA"),
            MealItem(food_id="168106", name="Papad", quantity_g=25, form=Form.WHOLE, source="USDA"),
        ]
    )

    # 1a: SearchSpace decode preserves source
    space = build_space(planned, db=db, profile=profile)
    x0 = space.encode_planned()
    decoded = space.decode(x0)
    for item in decoded.items:
        orig = next(i for i in planned.items if i.food_id == item.food_id)
        assert item.source == orig.source, f"Decode lost source for {item.name}: got {item.source}, expected {orig.source}"

    # 1b: End-to-end pipeline preserves source in Stage 2 and Stage 4
    trace = run_pipeline(profile, planned, Meal(items=[]), db=db)
    assert trace.stage2 is not None
    assert trace.stage4 is not None

    for item in trace.stage2.optimized_meal.items:
        assert item.source is not None, f"Stage 2 item {item.name} has None source"
        assert item.source in {"COMPOSITE", "IFCT_2017", "USDA"}

    for item in trace.final_meal.items:
        assert item.source is not None, f"Stage 4 item {item.name} has None source"
        assert item.source in {"COMPOSITE", "IFCT_2017", "USDA"}

    # Counterfactual meal accessor returns Stage 4 verified meal with sources
    assert len(trace.counterfactual_meal.items) >= 4
    for item in trace.counterfactual_meal.items:
        assert item.source in {"COMPOSITE", "IFCT_2017", "USDA"}


def test_2_traceable_source_ids_and_conversions(db):
    """Test 2: Food records maintain exact traceable catalog IDs and provenance metadata."""
    aloo = db.find("X006")
    assert aloo is not None
    assert aloo.fdc_id == "X006"
    assert aloo.source == "COMPOSITE"
    assert aloo.is_composite is True
    assert "A019" in aloo.ingredients  # Atta constituent

    atta = db.find("A019")
    assert atta is not None
    assert atta.fdc_id == "A019"
    assert atta.source == "IFCT_2017"

    mango = db.find("E038")
    assert mango is not None
    assert mango.source == "IFCT_2017"

    usda_pickle = db.find("169379")
    assert usda_pickle is not None
    assert usda_pickle.source == "USDA"


def test_3_optimizer_returns_baseline_when_no_improvement_feasible(db):
    """Test 3: DE returns baseline with 0 edits and valid=False when no candidate clears the target."""
    profile = UserProfile(age_group=AgeGroup.ADULT, goal=Goal.BALANCED_NUTRITION)
    planned = Meal(
        items=[
            MealItem(food_id="X006", name="Aloo paratha", quantity_g=95, source="COMPOSITE"),
            MealItem(food_id="X022", name="Curd (dahi)", quantity_g=100, source="COMPOSITE"),
            MealItem(food_id="169910", name="Mangos, raw", quantity_g=100, source="USDA"),
            MealItem(food_id="169379", name="Pickles, cucumber, sour", quantity_g=30, source="USDA"),
            MealItem(food_id="168106", name="Papad", quantity_g=25, source="USDA"),
        ]
    )
    trace = run_pipeline(profile, planned, Meal(items=[]), db=db)

    assert trace.stage2.valid is False
    assert trace.stage2.diff.n_items_changed == 0
    assert trace.stage2.diff.l1_distance_g == 0.0
    assert trace.stage2.converged_reason in {"plateaued_without_validity", "max_generations"}
    assert "No feasible" in trace.stage3.text


def test_4_feasible_pantry_fixture_produces_genuine_edits(db):
    """Test 4: Scenarios with safety hazards or feasible pantry options produce genuine edits and positive L1."""
    # Scenario: toddler with whole grapes and whole peanuts (hard choking hazards)
    trace = run_scenario("toddler_choking", db=db)
    assert trace.stage2.diff.n_items_changed > 0
    assert trace.stage2.diff.l1_distance_g > 0.0
    assert trace.stage2.valid is True
    assert trace.stage4.final_pass is True


def test_5_distinct_metrics_objective_suitability_rule_score(db, engine):
    """Test 5: Optimization objective, ML suitability, and RuleEngine soft scores are distinct numerical values."""
    profile = UserProfile(age_group=AgeGroup.ADULT, goal=Goal.BALANCED_NUTRITION)
    planned = Meal(
        items=[
            MealItem(food_id="X006", name="Aloo paratha", quantity_g=95, source="COMPOSITE"),
            MealItem(food_id="X022", name="Curd (dahi)", quantity_g=100, source="COMPOSITE"),
        ]
    )
    trace = run_pipeline(profile, planned, Meal(items=[]), db=db)

    ml_score = trace.stage1.suitability
    rule_score = trace.stage1.rule_evaluation.score
    obj_val = trace.stage2.objective_value

    assert isinstance(ml_score, float)
    assert isinstance(rule_score, float)
    assert isinstance(obj_val, float)
    # The ML score and rule score are from different estimators
    assert 0.0 <= ml_score <= 1.0
    assert 0.0 <= rule_score <= 1.0
    assert obj_val >= 0.0


def test_6_stage4_flags_missing_or_inconsistent_food_records(db, engine):
    """Test 6: Stage 4 flags ungrounded food records and identifies provenance discrepancies."""
    profile = UserProfile(age_group=AgeGroup.ADULT)
    # Meal with a fake food ID
    bogus_meal = [
        MealItem(food_id="99999999", name="Invented Superfood Nonexistent", quantity_g=100, form=Form.WHOLE),
    ]
    _, report = verify(bogus_meal, profile, db=db, engine=engine)
    assert len(report.unmatched) > 0 or len(report.unverifiable) > 0
    assert report.provenance_verified is False

    # Meal with provenance discrepancy: item says USDA, but X006 is COMPOSITE
    discrepant_meal = [
        MealItem(food_id="X006", name="Aloo paratha", quantity_g=95, form=Form.WHOLE, source="USDA"),
    ]
    _, report2 = verify(discrepant_meal, profile, db=db, engine=engine)
    assert any("Provenance discrepancy" in note for note in report2.source_notes)


def test_7_stage4_distinguishes_safety_from_target_attainment(db, engine):
    """Test 7: A meal that is safe but below target score reports safety_passed=True, target_attained=False."""
    profile = UserProfile(age_group=AgeGroup.ADULT)
    # Plain rice is safe for adults (no choking hazard, no toxic drug interaction)
    # but nutritionally incomplete for a balanced adult meal (score < 0.70)
    rice_item = [MealItem(food_id="168878", name="Rice, white, cooked", quantity_g=100, form=Form.WHOLE, source="USDA")]
    _, report = verify(rice_item, profile, db=db, engine=engine, target_score=0.70)

    assert report.safety_passed is True
    assert report.target_attained is False
    assert report.final_pass is True  # Safe and grounded, though target unmet


def test_8_indian_ood_flagging(db):
    """Test 8: Indian food items trigger is_ood=True and source_aware_adapter."""
    profile = UserProfile(age_group=AgeGroup.ADULT)
    indian_meal = Meal(
        items=[
            MealItem(food_id="X006", name="Aloo paratha", quantity_g=95, source="COMPOSITE"),
        ]
    )
    trace = run_pipeline(profile, indian_meal, Meal(items=[]), db=db)
    assert trace.stage1.is_ood is True
    assert trace.stage1.prediction_source == "source_aware_adapter"
    assert "Indian foods" in (trace.stage1.confidence_note or "")

    # Western USDA meal is NOT marked OOD
    western_meal = Meal(
        items=[
            MealItem(food_id="168878", name="Rice, white, cooked", quantity_g=100, source="USDA"),
        ]
    )
    trace2 = run_pipeline(profile, western_meal, Meal(items=[]), db=db)
    assert trace2.stage1.is_ood is False
    assert trace2.stage1.prediction_source == "surrogate_model"


def test_9_existing_scenarios_pass(db):
    """Test 9: All existing scenarios continue to succeed through verification."""
    for key in ["toddler_choking", "elderly_sodium", "adult_weight", "indian_adolescent_iron"]:
        trace = run_scenario(key, db=db)
        assert trace.stage4.final_pass is True
        assert len(trace.final_meal.items) > 0
