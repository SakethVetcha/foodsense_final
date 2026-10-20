"""Composite Indian dishes expressed as IFCT 2017 ingredient composites.

IFCT 2017 is a table of *raw foods* -- it has "Rice, parboiled, milled", not
"Idli". A meal planner for Indian diets needs the dishes people actually eat, so
this module defines each common dish as a small ingredient list whose codes are
IFCT food codes and whose grams are the amount used to prepare one reference
serving.

The nutrient composition of a dish is then *computed* -- never invented -- by
summing the composition of its ingredients from the IFCT table itself. That keeps
every number in the planner traceable to IFCT 2017 while still letting the demo
talk about idli, sambar and palak paneer rather than only raw millet.

Ingredients are pinned by IFCT code (e.g. ``A014`` = "Rice, parboiled, milled")
so a dish cannot silently re-resolve to a different food, exactly as the USDA
scenarios pin ``fdc_id``. If a code is missing from the table, the builder fails
loudly rather than quietly dropping the ingredient.

``yield_g`` is the cooked/served weight of the reference portion. When it is left
as ``None`` the ingredient sum is used, i.e. the composition is stored per 100 g
of the ingredient mix. Set it lower than the ingredient sum for dishes that lose
water on cooking (a dal reduces), so the per-100 g figures reflect the dish as
eaten rather than as assembled.

Sources
    IFCT 2017 -- Longvah T, Ananthan R, Bhaskarachary K, Venkaiah K (2017).
    Indian Food Composition Tables. National Institute of Nutrition, ICMR.
    https://www.nin.res.in/ebooks/IFCT2017.pdf
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["DISHES", "Dish", "diet_of_ifct_tags"]


@dataclass(frozen=True, slots=True)
class Dish:
    """One composite dish: a reference portion built from IFCT ingredients."""

    code: str
    name: str
    ingredients: dict[str, float]
    slots: tuple[str, ...]
    tags: tuple[str, ...] = ()
    #: Cooked/served weight of the reference portion. ``None`` == ingredient sum.
    yield_g: float | None = None
    #: Diet class of the dish: one of vegetarian / eggetarian / non_vegetarian.
    diet: str = "vegetarian"
    note: str = ""

    @property
    def ingredient_mass_g(self) -> float:
        return sum(self.ingredients.values())

    @property
    def serving_g(self) -> float:
        return self.yield_g if self.yield_g is not None else self.ingredient_mass_g


def diet_of_ifct_tags(tags: frozenset[str] | set[str]) -> str:
    """Map IFCT's diet tags onto the three classes the planner filters on.

    IFCT marks a food with the ``vegetarian`` / ``eggetarian`` / ``fishetarian``
    / ``nonveg`` labels that a food *is compatible with*. A plant food carries
    vegetarian; an egg dish carries eggetarian but not vegetarian; meat carries
    ``nonveg``. We keep the most restrictive class the food satisfies.
    """
    if "vegetarian" in tags:
        return "vegetarian"
    if "eggetarian" in tags:
        return "eggetarian"
    return "non_vegetarian"


# ---------------------------------------------------------------------------
# The dish catalogue
# ---------------------------------------------------------------------------
#
# Grams are the raw ingredient amounts for one reference serving. They follow
# common Indian home-cooking quantities; the *composition* is entirely IFCT.
# `yield_g` is set for dishes that visibly change mass on cooking.

DISHES: tuple[Dish, ...] = (
    # --- breakfast -------------------------------------------------------
    Dish(
        "X001",
        "Idli",
        {"A014": 55.0, "B003": 18.0},
        ("breakfast",),
        ("south_indian", "fermented"),
        yield_g=95.0,
        note="Rice + black gram, steamed.",
    ),
    Dish(
        "X002",
        "Plain dosa",
        {"A015": 45.0, "B003": 14.0, "T005": 4.0},
        ("breakfast", "dinner"),
        ("south_indian", "fermented"),
        yield_g=80.0,
    ),
    Dish(
        "X003",
        "Vegetable upma",
        {"A022": 50.0, "T012": 5.0, "G017": 15.0, "F002": 15.0, "D061": 10.0},
        ("breakfast",),
        ("south_indian",),
        yield_g=100.0,
    ),
    Dish(
        "X004",
        "Poha (flattened rice)",
        {"A011": 50.0, "T005": 6.0, "G017": 15.0, "D075": 10.0},
        ("breakfast", "snacks"),
        ("west_indian",),
        yield_g=85.0,
    ),
    Dish(
        "X005",
        "Chapati (roti)",
        {"A019": 45.0, "T005": 3.0},
        ("breakfast", "lunch", "dinner"),
        ("north_indian",),
        yield_g=60.0,
        note="Whole-wheat atta, one large roti.",
    ),
    Dish(
        "X006",
        "Aloo paratha",
        {"A019": 45.0, "F006": 40.0, "T013": 6.0},
        ("breakfast",),
        ("north_indian",),
        yield_g=95.0,
    ),
    Dish(
        "X007",
        "Dalia (broken-wheat) porridge",
        {"A021": 40.0, "L002": 150.0},
        ("breakfast",),
        ("high_fibre",),
        yield_g=180.0,
    ),
    Dish(
        "X008",
        "Masala omelette",
        {"M007": 90.0, "G017": 10.0, "T012": 4.0},
        ("breakfast",),
        ("high_protein",),
        yield_g=100.0,
        diet="eggetarian",
    ),
    # --- snacks ----------------------------------------------------------
    Dish(
        "X020",
        "Sprouts chaat (moong)",
        {"B011": 50.0, "G017": 15.0, "D075": 15.0, "E033": 3.0},
        ("snacks",),
        ("high_fibre", "high_protein"),
    ),
    Dish(
        "X021",
        "Roasted chana",
        {"B002": 30.0},
        ("snacks",),
        ("high_protein", "high_fibre"),
    ),
    Dish(
        "X022",
        "Curd (dahi)",
        {"L002": 100.0},
        ("snacks", "lunch", "dinner"),
        ("dairy",),
        diet="vegetarian",
        note="Set curd; composition approximated from whole cow milk.",
    ),
    Dish(
        "X023",
        "Fruit-and-nut bowl",
        {"E009": 80.0, "E001": 60.0, "H001": 12.0},
        ("snacks", "breakfast"),
        ("high_fibre",),
    ),
    # --- lunch / dinner --------------------------------------------------
    Dish(
        "X030",
        "Steamed rice",
        {"A015": 80.0},
        ("lunch", "dinner"),
        ("staple",),
        yield_g=200.0,
        note="80 g raw milled rice, as served.",
    ),
    Dish(
        "X031",
        "Dal (red gram / toor)",
        {"B021": 35.0, "T005": 3.0, "G017": 10.0, "D075": 10.0, "G033": 1.0},
        ("lunch", "dinner"),
        ("high_protein", "staple"),
        yield_g=150.0,
    ),
    Dish(
        "X032",
        "Dal (green gram / moong)",
        {"B010": 35.0, "T012": 3.0, "G017": 10.0, "G033": 1.0},
        ("lunch", "dinner"),
        ("high_protein", "easily_digested"),
        yield_g=150.0,
    ),
    Dish(
        "X033",
        "Rajma curry",
        {"B019": 45.0, "T005": 4.0, "G017": 15.0, "D075": 15.0, "G033": 1.0},
        ("lunch", "dinner"),
        ("high_protein", "high_fibre"),
        yield_g=160.0,
    ),
    Dish(
        "X034",
        "Chole (chickpea curry)",
        {"B002": 45.0, "T005": 4.0, "G017": 15.0, "D075": 15.0, "G033": 1.0},
        ("lunch", "dinner"),
        ("high_protein", "high_fibre"),
        yield_g=160.0,
    ),
    Dish(
        "X035",
        "Sambar",
        {"B021": 25.0, "D046": 25.0, "G017": 10.0, "T005": 3.0},
        ("lunch", "dinner"),
        ("south_indian",),
        yield_g=150.0,
    ),
    Dish(
        "X036",
        "Mixed vegetable sabzi",
        {"F006": 50.0, "D036": 30.0, "D061": 20.0, "T012": 5.0, "G017": 10.0},
        ("lunch", "dinner"),
        ("high_fibre",),
        yield_g=110.0,
    ),
    Dish(
        "X037",
        "Palak paneer",
        {"C033": 80.0, "L003": 40.0, "T013": 4.0, "G017": 10.0},
        ("lunch", "dinner"),
        ("high_protein", "iron_rich"),
        yield_g=130.0,
    ),
    Dish(
        "X038",
        "Bhindi (okra) sabzi",
        {"D056": 70.0, "T012": 5.0, "G017": 10.0},
        ("lunch", "dinner"),
        ("high_fibre",),
        yield_g=85.0,
    ),
    Dish(
        "X039",
        "Curd rice",
        {"A015": 70.0, "L002": 80.0, "G010": 2.0},
        ("lunch", "dinner"),
        ("south_indian",),
        yield_g=160.0,
    ),
    Dish(
        "X040",
        "Khichdi",
        {"A015": 50.0, "B010": 25.0, "T012": 4.0, "G017": 10.0},
        ("lunch", "dinner"),
        ("balanced", "easily_digested"),
        yield_g=170.0,
    ),
    Dish(
        "X041",
        "Vegetable pulao",
        {"A015": 60.0, "F002": 20.0, "D061": 15.0, "T012": 5.0, "G017": 10.0},
        ("lunch", "dinner"),
        ("balanced",),
        yield_g=180.0,
    ),
    Dish(
        "X042",
        "Chicken curry",
        {"N003": 100.0, "G017": 30.0, "D075": 30.0, "T012": 5.0, "G033": 2.0},
        ("lunch", "dinner"),
        ("high_protein", "iron_rich"),
        yield_g=140.0,
        diet="non_vegetarian",
    ),
    Dish(
        "X043",
        "Fish curry (rohu)",
        {"S006": 100.0, "G017": 20.0, "D075": 20.0, "T005": 4.0},
        ("lunch", "dinner"),
        ("high_protein", "omega3"),
        yield_g=130.0,
        diet="non_vegetarian",
    ),
    Dish(
        "X044",
        "Egg curry",
        {"M004": 100.0, "G017": 30.0, "D075": 30.0, "T012": 4.0},
        ("lunch", "dinner"),
        ("high_protein",),
        yield_g=130.0,
        diet="eggetarian",
    ),
    Dish(
        "X045",
        "Palak dal (spinach + lentil)",
        {"B013": 30.0, "C033": 60.0, "T005": 3.0, "G017": 10.0},
        ("lunch", "dinner"),
        ("iron_rich", "high_protein"),
        yield_g=150.0,
    ),
    Dish(
        "X046",
        "Ragi mudde (finger-millet ball)",
        {"A010": 60.0},
        ("lunch", "dinner"),
        ("millet", "calcium_rich"),
        yield_g=180.0,
    ),
    Dish(
        "X047",
        "Bajra roti (pearl-millet roti)",
        {"A003": 50.0, "T013": 3.0},
        ("lunch", "dinner"),
        ("millet", "high_fibre"),
        yield_g=65.0,
    ),
)
