"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from foodsense import PROJECT_ROOT, SEED
from foodsense.schemas import AgeGroup, Form, Goal, Meal, MealItem, UserProfile

# On Windows, LightGBM's native C library can fail with an access violation if
# another C library (such as scikit-learn's vcomp140.dll) initializes OpenMP first.
# Performing a dummy prediction here initializes LightGBM's OpenMP runtime safely.
try:
    from foodsense import MODELS_DIR

    _lgb_path = MODELS_DIR / "stage1_lightgbm.txt"
    if _lgb_path.exists():
        import lightgbm as _lgb
        import numpy as _np

        _dummy = _lgb.Booster(model_file=str(_lgb_path))
        _dummy.predict(_np.zeros((1, 41), dtype=_np.float64))
except Exception:
    pass


@pytest.fixture(scope="session")
def project_root():
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def seed() -> int:
    return SEED


@pytest.fixture
def toddler_profile() -> UserProfile:
    """The `toddler_choking` scenario profile: 18 months, balanced nutrition, iron focus."""
    from foodsense.schemas import HealthFlag

    return UserProfile(
        age_group=AgeGroup.TODDLER,
        age_months=18,
        weight_kg=11.0,
        goal=Goal.BALANCED_NUTRITION,
        health_flags=[HealthFlag.IRON_FOCUS],
    )


@pytest.fixture
def toddler_planned_meal() -> Meal:
    """Whole grapes + whole peanuts + plain rice -- two choking hazards by construction."""
    return Meal(
        items=[
            MealItem(food_id="174683", name="Grapes, raw", quantity_g=40.0, form=Form.WHOLE),
            MealItem(food_id="172430", name="Peanuts, raw", quantity_g=20.0, form=Form.WHOLE),
            MealItem(
                food_id="169756", name="Rice, white, cooked", quantity_g=50.0, form=Form.WHOLE
            ),
        ]
    )
