"""HTTP tests for the Indian meal-planner endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from foodsense import INDIA_FOOD_DB_PARQUET
from foodsense.api.main import app

pytestmark = pytest.mark.skipif(
    not INDIA_FOOD_DB_PARQUET.exists(),
    reason="Indian food database not built; run `python -m foodsense.data.build_indian_food_db`",
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


SAMPLE = "Hemoglobin 10.2 g/dL\nHbA1c 6.1 %\nTriglycerides 190 mg/dL\n"

VALID_PROFILE = {
    "age_years": 14,
    "sex": "female",
    "weight_kg": 45,
    "activity": "moderate",
    "diet": "vegetarian",
    "goal": "balanced",
}


class TestPlanEndpoint:
    def test_returns_four_meals_and_the_day(self, client):
        body = client.post("/api/plan", json=VALID_PROFILE).json()
        assert [m["slot"] for m in body["meals"]] == ["breakfast", "lunch", "dinner", "snacks"]
        assert body["day_nutrients"]["energy_kcal"] > 0
        assert body["nutrient_table"]
        assert body["life_stage"] == "teen_13_15"

    def test_personalised_response_is_not_cached(self, client):
        r = client.post("/api/plan", json=VALID_PROFILE)
        assert r.headers.get("cache-control") == "no-store, private"

    def test_age_boundaries(self, client):
        r5 = client.post("/api/plan", json={**VALID_PROFILE, "age_years": 5})
        assert r5.status_code == 200
        r20 = client.post("/api/plan", json={**VALID_PROFILE, "age_years": 20})
        assert r20.status_code == 200
        r4 = client.post("/api/plan", json={**VALID_PROFILE, "age_years": 4})
        assert r4.status_code == 422
        r21 = client.post("/api/plan", json={**VALID_PROFILE, "age_years": 21})
        assert r21.status_code == 422

    def test_rejects_an_age_outside_5_to_20(self, client):
        r = client.post("/api/plan", json={**VALID_PROFILE, "age_years": 3})
        assert r.status_code == 422
        assert r.json()["error"] == "invalid_request"

    def test_rejects_an_unknown_field(self, client):
        r = client.post("/api/plan", json={**VALID_PROFILE, "nonsense": 1})
        assert r.status_code == 422

    def test_respects_allergies_and_regional_pref(self, client):
        payload = {
            **VALID_PROFILE,
            "regional_preference": "south_indian",
            "allergies": ["dairy", "gluten"],
        }
        body = client.post("/api/plan", json=payload).json()
        assert body["meals"]
        item_names = [item["name"].lower() for m in body["meals"] for item in m["items"]]
        assert not any("roti" in name or "milk" in name or "curd" in name or "paneer" in name for name in item_names)

    def test_lab_text_flows_into_the_plan(self, client):
        payload = {**VALID_PROFILE, "lab_text": "Hemoglobin 10.0 g/dL"}
        body = client.post("/api/plan", json=payload).json()
        assert body["lab_report"]["markers"][0]["key"] == "hemoglobin"


class TestLabReportEndpoint:
    def test_parses_and_interprets(self, client):
        body = client.post("/api/lab-report", json={"text": SAMPLE, "sex": "female"}).json()
        assert {m["key"] for m in body["markers"]} >= {"hemoglobin", "hba1c", "triglycerides"}
        assert body["findings"]
        assert "disclaimer" in body

    def test_not_cached(self, client):
        r = client.post("/api/lab-report", json={"text": "hemoglobin 13"})
        assert r.headers.get("cache-control") == "no-store, private"

    def test_empty_text_is_rejected(self, client):
        r = client.post("/api/lab-report", json={"text": ""})
        assert r.status_code == 422


class TestMetadataEndpoints:
    def test_life_stages_are_listed_with_their_sex_splits(self, client):
        body = client.get("/api/life-stages").json()
        assert len(body) == 6
        assert body[0]["min_age"] == 5
        assert body[-1]["max_age"] == 20
        # The adolescent bands are the sex-specific ones.
        teen = next(s for s in body if s["key"] == "teen_13_15")
        assert teen["sex_specific"] is True
        assert teen["iron_mg"]["female"] > teen["iron_mg"]["male"]

    def test_health_reports_the_indian_database(self, client):
        body = client.get("/api/health").json()
        assert body["n_indian_foods"] > 400

    def test_indian_foods_can_be_filtered_by_slot_and_diet(self, client):
        from foodsense.data.fdc import get_indian_food_db

        db = get_indian_food_db()
        body = client.get(
            "/api/indian-foods", params={"slot": "breakfast", "diet": "vegetarian"}
        ).json()
        assert body
        for food in body:
            tags = db.get(food["food_id"]).tags
            assert "meal_breakfast" in tags
            assert "diet_vegetarian" in tags

    def test_indian_foods_search_finds_a_dish(self, client):
        body = client.get("/api/indian-foods", params={"q": "idli"}).json()
        assert any(f["name"] == "Idli" for f in body)

    def test_food_alternatives_endpoint(self, client):
        body = client.get(
            "/api/food-alternatives", params={"slot": "breakfast", "diet": "vegetarian"}
        ).json()
        assert isinstance(body, list)
        assert len(body) > 0
        assert all("food_id" in item and "energy_kcal" in item for item in body)

    def test_body_metrics_endpoint(self, client):
        body = client.post(
            "/api/body-metrics",
            json={"age_years": 14, "sex": "female", "height_cm": 155, "weight_kg": 48},
        ).json()
        assert body["bmi"] == 20.0
        assert "estimated_bmr_kcal" in body
        assert body["bmi_category"]

    def test_recalculate_plan_endpoint(self, client):
        plan_body = client.post("/api/plan", json=VALID_PROFILE).json()
        meals = plan_body["meals"]
        # Double quantity of first item
        meals[0]["items"][0]["quantity_g"] *= 2
        recalc = client.post(
            "/api/recalculate-plan", json={"profile": VALID_PROFILE, "meals": meals}
        ).json()
        assert recalc["meals"][0]["items"][0]["quantity_g"] == meals[0]["items"][0]["quantity_g"]
        assert recalc["day_nutrients"]["energy_kcal"] > 0
        assert recalc["day_macro_shares"]["carbohydrate"] > 0
