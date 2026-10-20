"""FastAPI app: the pipeline over HTTP, plus the built single-page frontend.

    POST /api/recommend   -> a full PipelineTrace, verbatim
    GET  /api/scenarios   -> the three preloaded demo scenarios
    GET  /api/providers   -> which Stage-3 providers are usable right now
    GET  /api/foods?q=    -> food-database autocomplete
    GET  /api/health      -> liveness probe
    GET  /                -> frontend/dist/index.html, when it has been built

**The trace is the contract.** `/api/recommend` returns `PipelineTrace` exactly as
the pipeline produced it -- no response wrapper, no reshaping, no second model
that could drift from the first. The UI's stepper, the acceptance tests and the
JSON viewer are all reading the same document. Anything the UI needs that the
trace lacks is a reason to extend the trace, not to add a parallel path.

**Degraded is not failed.** A provider with no key is not an error condition: the
run completes on the offline template with `stage3.fallback_used` set and the
reason in `warnings`, and returns 200. The UI shows a badge. The only 4xx
responses here are for requests that are actually malformed or name something
that does not exist.

**Local by default.** `foodsense serve` binds 127.0.0.1, which is the whole
security boundary -- there is no auth, and there should not be, because there is
nothing here to authenticate against. API keys are read from the server's own
environment and never travel to the browser.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from foodsense import __version__
from foodsense.api.models import (
    CustomRequest,
    FoodSummary,
    HealthResponse,
    LabReportRequest,
    LifeStageSummary,
    ProviderInfo,
    ScenarioRequest,
    ScenarioSummary,
)
from foodsense.data.fdc import get_food_db, get_indian_food_db
from foodsense.schemas import Meal, PipelineTrace


def _find_frontend_dist() -> Path:
    """Locate the built UI, from wherever this package happens to be installed.

    This used to be a single path relative to the repo root, which quietly
    assumed the process was started *in* a source checkout. It is not: the CLI
    is installed, and `foodsense serve` run from any other directory could not
    even import this module, let alone find the bundle.

    Three places, in order of specificity:

    1. ``FOODSENSE_FRONTEND_DIST`` -- an explicit override, for anyone serving a
       bundle built elsewhere.
    2. ``static/`` inside this package -- where a packaged build would live.
    3. ``frontend/dist`` in an ancestor directory -- the source-checkout case,
       found by walking up from this file rather than from the current working
       directory, so it does not matter where the process was started.

    Returns the first that exists; failing all three, returns the packaged path
    so the caller has something concrete to report as missing. A missing bundle
    is not an error -- the API is useful without it and `foodsense serve` says so.
    """
    override = os.environ.get("FOODSENSE_FRONTEND_DIST")
    if override:
        return Path(override).expanduser().resolve()

    packaged = Path(__file__).resolve().parent / "static"
    if (packaged / "index.html").exists():
        return packaged

    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / "frontend" / "dist"
        if (candidate / "index.html").exists():
            return candidate
    return packaged


#: Built frontend, resolved once at import.
FRONTEND_DIST = _find_frontend_dist()

#: Dev-mode origins allowed to call the API cross-origin. Only ever localhost:
#: in the shipped shape the frontend is served by this same app, so there is no
#: cross-origin request to permit at all.
DEV_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

app = FastAPI(
    title="FoodSense",
    version=__version__,
    description="Availability-aware, verification-guided counterfactual food recommendation.",
)

# CORS is opt-in and localhost-only. `FOODSENSE_DEV=1` is set by the Vite dev
# workflow; the demo path never sets it and therefore allows no cross-origin
# request whatsoever.
if os.environ.get("FOODSENSE_DEV") == "1":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_ORIGINS),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


# ---------------------------------------------------------------------------
# Errors: one shape, and never an internal detail
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def _http_error(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": _ERROR_LABELS.get(exc.status_code, "error"), "detail": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    """Deliberately opaque.

    An exception string can carry a file path, a query, or -- the reason this
    handler exists -- an API key echoed back by an SDK. The type name is enough
    for a demo operator to know something broke; the traceback stays in the
    server log where it belongs.
    """
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": f"{type(exc).__name__} while handling the request; see the server log.",
        },
    )


_ERROR_LABELS = {404: "not_found", 422: "invalid_request", 400: "invalid_request"}


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness, plus the two facts that decide whether a demo will work."""
    from foodsense.stage1_prediction.predict import LIGHTGBM_PATH

    db = get_food_db()
    try:
        n_indian = len(get_indian_food_db().records)
    except Exception:
        n_indian = 0
    return HealthResponse(
        status="ok",
        version=__version__,
        model_loaded=LIGHTGBM_PATH.exists(),
        n_foods=len(db.records),
        n_indian_foods=n_indian,
        default_provider="template",
    )


@app.get("/api/scenarios", response_model=list[ScenarioSummary])
def scenarios() -> list[ScenarioSummary]:
    """The built-in demo cases, as the dropdown needs them."""
    from foodsense.scenarios import SCENARIOS

    db = get_food_db()
    return [
        ScenarioSummary(
            key=key,
            title=scenario.title,
            description=scenario.description,
            age_group=scenario.profile.age_group.value,
            goal=scenario.profile.goal.value,
            health_flags=[f.value for f in scenario.profile.health_flags],
            n_planned_items=len(scenario.planned_meal(db).items),
            n_pantry_items=len(scenario.pantry_meal(db).items),
        )
        for key, scenario in SCENARIOS.items()
    ]


@app.get("/api/providers", response_model=list[ProviderInfo])
def providers() -> list[ProviderInfo]:
    """Which Stage-3 providers are usable, and why the others are not.

    The UI greys out the unavailable ones and shows the reason, so "no API key"
    presents as a deliberate offline default rather than as something broken.
    """
    from foodsense.stage3_rag.providers import PROVIDERS, get_provider

    out: list[ProviderInfo] = []
    for name in PROVIDERS:
        provider = get_provider(name)
        available = provider.available
        out.append(
            ProviderInfo(
                name=name,
                available=available,
                reason="" if available else provider.unavailable_reason(),
                is_default=name == "template",
            )
        )
    return out


@app.get("/api/foods", response_model=list[FoodSummary])
def foods(
    q: str = Query(default="", max_length=100, description="substring or fuzzy name query"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[FoodSummary]:
    """Autocomplete over the curated database."""
    db = get_food_db()
    # search() ranks and returns (record, score) pairs; the score is the matcher's
    # business, not the UI's.
    records = (
        [record for record, _ in db.search(q, limit=limit)] if q.strip() else db.records[:limit]
    )
    return [
        FoodSummary(
            food_id=r.fdc_id,
            name=r.name,
            category=r.category,
            energy_kcal_per_100g=round(r.nutrients_per_100g.energy_kcal, 1),
            allowed_forms=[f.value for f in r.allowed_forms],
            hazard_class=r.hazard_class or None,
        )
        for r in records
    ]


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------


@app.post("/api/recommend", response_model=PipelineTrace)
def recommend(payload: dict[str, Any]) -> PipelineTrace:
    """Run all four stages and return the trace verbatim.

    Accepts either shape. Which one was sent is decided by the presence of
    ``scenario`` rather than by trying both and keeping whichever parsed, so a
    typo in a custom payload reports *that* typo instead of "not a scenario".
    """
    from pydantic import ValidationError

    from foodsense.pipeline import run_pipeline, run_scenario
    from foodsense.stage3_rag.providers import get_provider

    is_scenario = "scenario" in payload
    try:
        request = ScenarioRequest(**payload) if is_scenario else CustomRequest(**payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc

    try:
        provider = get_provider(request.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if isinstance(request, ScenarioRequest):
        from foodsense.scenarios import SCENARIOS

        if request.scenario not in SCENARIOS:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Unknown scenario {request.scenario!r}. "
                    f"Available: {', '.join(sorted(SCENARIOS))}."
                ),
            )
        return run_scenario(request.scenario, provider=provider, seed=request.seed)

    if not request.planned_meal.items:
        raise HTTPException(status_code=422, detail="planned_meal must contain at least one item.")

    db = get_food_db()
    unknown = db.unknown_ids(request.planned_meal) + db.unknown_ids(Meal(items=request.pantry))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown food ids: {', '.join(sorted(set(unknown))[:5])}.",
        )

    return run_pipeline(
        request.profile,
        request.planned_meal,
        request.pantry,
        provider=provider,
        seed=request.seed,
    )


def _first_error(exc: Exception) -> str:
    """One readable line from a pydantic error, without dumping the whole tree."""
    errors = getattr(exc, "errors", None)
    if not callable(errors):
        return str(exc)
    first = (errors() or [{}])[0]
    location = ".".join(str(p) for p in first.get("loc", ())) or "body"
    return f"{location}: {first.get('msg', 'invalid value')}"


# ---------------------------------------------------------------------------
# Indian meal planner (ages 5-20, ICMR-NIN 2020)
# ---------------------------------------------------------------------------


@app.get("/api/life-stages", response_model=list[LifeStageSummary])
def life_stages() -> list[LifeStageSummary]:
    """The ICMR-NIN 2020 age bands the planner covers, with their sex splits."""
    from foodsense.nutrition import load_life_stage_config
    from foodsense.schemas import LifeStage, Sex

    out: list[LifeStageSummary] = []
    for stage in LifeStage:
        cfg = load_life_stage_config(stage)

        def by_sex(key: str) -> dict[str, float]:
            return {
                sex.value: float(cfg.resolved(sex).get(key, 0.0)) for sex in (Sex.MALE, Sex.FEMALE)
            }

        out.append(
            LifeStageSummary(
                key=stage.value,
                label=cfg.label,
                min_age=cfg.age_range[0],
                max_age=cfg.age_range[1],
                sex_specific=bool(cfg.sex_daily["male"] or cfg.sex_daily["female"]),
                energy_kcal=by_sex("energy_kcal"),
                protein_g=by_sex("protein_g"),
                iron_mg=by_sex("iron_mg"),
                source=cfg.source,
            )
        )
    return out


@app.get("/api/indian-foods", response_model=list[FoodSummary])
def indian_foods(
    q: str = Query(default="", max_length=100),
    slot: str | None = Query(default=None, description="breakfast|lunch|dinner|snacks"),
    diet: str | None = Query(default=None, description="vegetarian|eggetarian|non_vegetarian"),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[FoodSummary]:
    """Search the Indian food database, optionally filtered by meal slot and diet."""
    db = get_indian_food_db()
    records = (
        [record for record, _ in db.search(q, limit=limit)] if q.strip() else db.records
    )
    compatible = {
        "vegetarian": {"vegetarian"},
        "eggetarian": {"vegetarian", "eggetarian"},
        "non_vegetarian": {"vegetarian", "eggetarian", "non_vegetarian"},
    }
    wanted = compatible.get(diet or "non_vegetarian", compatible["non_vegetarian"])

    out: list[FoodSummary] = []
    for r in records:
        if slot and f"meal_{slot}" not in r.tags:
            continue
        if diet and not any(f"diet_{d}" in r.tags for d in wanted):
            continue
        out.append(
            FoodSummary(
                food_id=r.fdc_id,
                name=r.name,
                category=r.category,
                energy_kcal_per_100g=round(r.nutrients_per_100g.energy_kcal, 1),
                allowed_forms=[f.value for f in r.allowed_forms],
                hazard_class=r.hazard_class or None,
            )
        )
        if len(out) >= limit:
            break
    return out


@app.post("/api/lab-report")
def lab_report(payload: dict[str, Any], response: Response) -> JSONResponse:
    """Interpret pasted lab values or digital PDF into non-diagnostic dietary findings.

    Deliberately stateless: nothing is written to disk or logged, and the
    response is marked ``no-store`` so neither the browser nor a proxy caches a
    person's health data.
    """
    import base64
    import io
    from foodsense.labs import analyze_lab_text

    try:
        request = LabReportRequest(**payload)
    except Exception as exc:  # pydantic ValidationError
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc

    raw_text = (request.text or "").strip()
    if request.pdf_base64:
        try:
            from pypdf import PdfReader

            pdf_bytes = base64.b64decode(request.pdf_base64)
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text = [page.extract_text() or "" for page in reader.pages]
            pdf_text = "\n".join(pages_text).strip()
            if pdf_text:
                raw_text = f"{raw_text}\n{pdf_text}".strip() if raw_text else pdf_text
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Unable to read PDF file: {exc}"
            ) from exc

    if not raw_text:
        raise HTTPException(status_code=422, detail="text cannot be empty.")

    report = analyze_lab_text(raw_text, sex=request.sex)
    response.headers["Cache-Control"] = "no-store, private"
    content = report.model_dump() if hasattr(report, "model_dump") else _asdict(report)
    content["extracted_text"] = raw_text
    return JSONResponse(content=content, headers={"Cache-Control": "no-store, private"})


@app.get("/api/food-alternatives")
def food_alternatives(
    slot: str = Query(..., description="breakfast|lunch|dinner|snacks"),
    diet: str = Query(default="vegetarian", description="vegetarian|eggetarian|non_vegetarian"),
    current_id: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Return appropriate Indian food alternatives for a given meal slot and diet."""
    from foodsense.planner import get_food_alternatives

    return get_food_alternatives(slot=slot, diet=diet, current_food_id=current_id, limit=limit)


@app.post("/api/recalculate-plan")
def recalculate_plan(payload: dict[str, Any], response: Response) -> JSONResponse:
    """Recalculate verified nutrition after food item substitutions or portion edits."""
    from pydantic import ValidationError
    from foodsense.planner import PlannerProfile, recalculate_meal_plan

    profile_data = payload.get("profile", {})
    meals_data = payload.get("meals", [])
    seed = int(payload.get("seed", 42))

    try:
        profile = PlannerProfile(**profile_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc

    if not meals_data:
        raise HTTPException(status_code=422, detail="meals must contain at least one meal.")

    result = recalculate_meal_plan(profile, meals_data, seed=seed)
    response.headers["Cache-Control"] = "no-store, private"
    return JSONResponse(content=result.model_dump(), headers={"Cache-Control": "no-store, private"})


@app.post("/api/body-metrics")
def body_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    """Calculate BMI, BMR, and nutritional assessment metrics according to ICMR-NIN 2020."""
    from foodsense.nutrition import calculate_body_metrics

    age = int(payload.get("age_years", 14))
    sex = str(payload.get("sex", "female"))
    height = float(payload["height_cm"]) if payload.get("height_cm") is not None else None
    weight = float(payload["weight_kg"]) if payload.get("weight_kg") is not None else None

    return calculate_body_metrics(age_years=age, sex=sex, height_cm=height, weight_kg=weight)


@app.post("/api/plan")
def plan(payload: dict[str, Any], response: Response) -> JSONResponse:
    """Build a personalised Indian meal plan for an ages 5-20 profile.

    Returns a ``MealPlan``: four meals (breakfast, lunch, dinner, snacks), the
    day's nutrient proportions, an actual-vs-target table for the charts, and any
    dietary findings from an optional lab report. Marked ``no-store`` because it
    may embed health data.
    """
    from pydantic import ValidationError

    from foodsense.planner import PlannerProfile, generate_meal_plan

    data = {k: v for k, v in payload.items() if k != "seed"}
    try:
        profile = PlannerProfile(**data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc

    result = generate_meal_plan(profile, seed=int(payload.get("seed", 42)))
    response.headers["Cache-Control"] = "no-store, private"
    return JSONResponse(content=result.model_dump(), headers={"Cache-Control": "no-store, private"})


def _asdict(obj: Any) -> Any:
    """Fallback serializer for the dataclass-based lab report."""
    import dataclasses

    if dataclasses.is_dataclass(obj):
        return {k: _asdict(v) for k, v in dataclasses.asdict(obj).items()}
    return obj


# ---------------------------------------------------------------------------
# The built frontend, mounted last so it cannot shadow /api
# ---------------------------------------------------------------------------

if (FRONTEND_DIST / "index.html").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")
