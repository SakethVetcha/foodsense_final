"""Optional laboratory-report interpretation (non-diagnostic).

A user may paste or upload the numbers from a routine blood report -- haemoglobin,
fasting glucose, HbA1c, a lipid panel, vitamin D, B12, ferritin, calcium, TSH.
This module parses those numbers, compares each against a reference range, and
turns the result into **dietary** guidance the planner can act on.

Three things it deliberately is not:

* **Not a diagnosis.** Every finding is phrased as a dietary focus, and the
  response carries an explicit "discuss with a clinician" disclaimer. The whole
  module is advisory.
* **Not OCR.** Reports arrive as *text* -- typed values, a pasted CSV, or a
  ``.txt``/``.csv``/``.md``/``.json`` file. Extracting numbers from a scanned PDF
  or a phone photo is a different, much less reliable problem (font, layout,
  units, handwriting), so it is not attempted here; the UI offers a paste box and
  a text-file upload instead, and says why. See ``docs/lab_reports.md``.
* **Not stored.** Nothing is written to disk or logged. The values live for the
  duration of the request and the response is marked ``Cache-Control: no-store``.

Reference ranges are the conventional adult/paediatric laboratory ranges cited in
the docstrings below. They are for screening context only, not clinical cut-offs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from foodsense.schemas import Sex

__all__ = [
    "KNOWN_MARKERS",
    "LabFinding",
    "LabMarker",
    "LabReport",
    "analyze_lab_text",
    "findings_for",
    "parse_lab_text",
]


# ---------------------------------------------------------------------------
# Marker catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MarkerSpec:
    """How to recognise one marker and what its numbers mean."""

    key: str
    label: str
    unit: str
    #: Substrings that identify the marker in free text (lower-cased, word-ish).
    aliases: tuple[str, ...]
    #: Conventional reference band. ``None`` means "lower is better, no ceiling".
    low: float | None
    high: float | None
    #: Units we accept, with the factor to convert into :attr:`unit`.
    unit_aliases: dict[str, float] = field(default_factory=dict)
    note: str = ""


#: mg/dL is the conventional unit for the lipid panel and glucose.
MARKERS: tuple[MarkerSpec, ...] = (
    MarkerSpec(
        key="hemoglobin",
        label="Haemoglobin",
        unit="g/dL",
        aliases=("haemoglobin", "hemoglobin", "hb"),
        low=12.0,
        high=17.0,
        note="Low haemoglobin suggests anaemia; iron and vitamin C matter dietarily.",
    ),
    MarkerSpec(
        key="ferritin",
        label="Ferritin",
        unit="ng/mL",
        aliases=("ferritin",),
        low=15.0,
        high=150.0,
        note="Ferritin is the body's iron store; low values point to depleted iron.",
    ),
    MarkerSpec(
        key="fasting_glucose",
        label="Fasting glucose",
        unit="mg/dL",
        aliases=("fasting glucose", "fasting blood sugar", "fbs", "fasting sugar", "glucose"),
        low=70.0,
        high=99.0,
        note="A fasting value of 100-125 mg/dL is the prediabetic range; >=126 is high.",
    ),
    MarkerSpec(
        key="hba1c",
        label="HbA1c",
        unit="%",
        aliases=("hba1c", "glycated haemoglobin", "glycated hemoglobin", "a1c"),
        low=None,
        high=5.7,
        note="5.7-6.4% is the prediabetic range; >=6.5% is the diabetic range.",
    ),
    MarkerSpec(
        key="total_cholesterol",
        label="Total cholesterol",
        unit="mg/dL",
        aliases=("total cholesterol", "cholesterol total", "cholesterol"),
        low=None,
        high=200.0,
        note="Below 200 mg/dL is desirable.",
    ),
    MarkerSpec(
        key="ldl",
        label="LDL cholesterol",
        unit="mg/dL",
        aliases=("ldl cholesterol", "ldl-c", "ldl"),
        low=None,
        high=100.0,
        note="Lower LDL is better; saturated fat is the main dietary lever.",
    ),
    MarkerSpec(
        key="hdl",
        label="HDL cholesterol",
        unit="mg/dL",
        aliases=("hdl cholesterol", "hdl-c", "hdl"),
        low=40.0,
        high=None,
        note="Higher HDL is protective; below 40 mg/dL is low.",
    ),
    MarkerSpec(
        key="triglycerides",
        label="Triglycerides",
        unit="mg/dL",
        aliases=("triglycerides", "triglyceride", "tg"),
        low=None,
        high=150.0,
        note="Below 150 mg/dL is desirable; refined carbohydrate raises it.",
    ),
    MarkerSpec(
        key="vitamin_d",
        label="Vitamin D (25-OH)",
        unit="ng/mL",
        aliases=("vitamin d", "25-oh vitamin d", "25 hydroxy vitamin d", "vit d"),
        low=30.0,
        high=100.0,
        note="Below 30 ng/mL is insufficient; sunlight and fortified foods help.",
    ),
    MarkerSpec(
        key="vitamin_b12",
        label="Vitamin B12",
        unit="pg/mL",
        aliases=("vitamin b12", "cobalamin", "b12"),
        low=200.0,
        high=900.0,
        note="Below 200 pg/mL is low; animal foods and fortified cereals supply B12.",
    ),
    MarkerSpec(
        key="calcium",
        label="Serum calcium",
        unit="mg/dL",
        aliases=("serum calcium", "calcium"),
        low=8.5,
        high=10.5,
        note="Serum calcium is tightly regulated; diet and vitamin D support bone health.",
    ),
    MarkerSpec(
        key="tsh",
        label="TSH",
        unit="mIU/L",
        aliases=("tsh", "thyroid stimulating hormone"),
        low=0.5,
        high=4.5,
        note="TSH outside the range may warrant an endocrine review.",
    ),
)

KNOWN_MARKERS: dict[str, MarkerSpec] = {m.key: m for m in MARKERS}

#: Unit strings we accept, mapped to the canonical unit per marker family.
_UNIT_FACTORS: dict[str, dict[str, float]] = {
    "mg/dL": {"mg/dl": 1.0, "mgdl": 1.0},
    "g/dL": {"g/dl": 1.0, "gdl": 1.0, "gm/dl": 1.0},
    "ng/mL": {"ng/ml": 1.0, "ngml": 1.0, "µg/l": 1.0, "ug/l": 1.0},
    "pg/mL": {"pg/ml": 1.0, "pgml": 1.0},
    "%": {"%": 1.0, "percent": 1.0},
    "mIU/L": {"miu/l": 1.0, "miu/ml": 1.0, "uiu/ml": 1.0},
}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
#: Characters allowed to follow a value as its unit (e.g. "mg/dL", "%", "ng/mL").
_UNIT_TAIL = re.compile(r"\s*([A-Za-z%/µ]+(?:/[A-Za-z]+)?)")

#: Alias -> marker, longest alias first, so "total cholesterol" beats "cholesterol".
_ALIAS_INDEX: tuple[tuple[str, MarkerSpec], ...] = tuple(
    sorted(
        ((alias, spec) for spec in MARKERS for alias in spec.aliases),
        key=lambda pair: -len(pair[0]),
    )
)


def _spec_for(name: str) -> MarkerSpec | None:
    text = name.strip().lower().replace("_", " ")
    # Longest alias first so "total cholesterol" beats "cholesterol".
    best: MarkerSpec | None = None
    best_len = -1
    for spec in MARKERS:
        for alias in spec.aliases:
            if alias in text and len(alias) > best_len:
                best, best_len = spec, len(alias)
    return best


def _match_line(line: str) -> tuple[MarkerSpec, float, str] | None:
    """Find the marker named on ``line`` and the value that follows it.

    Anchoring on the marker name and then taking the *first* number after it is
    far more robust than trying to parse the whole line: it handles "Hb: 10.2",
    "LDL 138", "Total Cholesterol - 215" and "Vitamin B12 180 pg/mL" alike, and it
    will not be fooled by a token like "B12" being split into a name and a value.
    """
    low = line.lower()
    for alias, spec in _ALIAS_INDEX:
        idx = low.find(alias)
        if idx == -1:
            continue
        # Require a word boundary around the alias so "hb" does not match "shb".
        before_ok = idx == 0 or not low[idx - 1].isalnum()
        after = idx + len(alias)
        after_ok = after >= len(low) or not low[after].isalnum()
        if not (before_ok and after_ok):
            continue
        rest = line[after:]
        number = _NUMBER.search(rest)
        if number is None:
            continue
        unit_match = _UNIT_TAIL.match(rest[number.end():])
        unit = unit_match.group(1) if unit_match else ""
        return spec, float(number.group()), unit
    return None


def _convert(spec: MarkerSpec, value: float, unit: str) -> float:
    """Convert ``value`` from ``unit`` into the marker's canonical unit."""
    u = unit.strip().lower()
    if not u:
        return value
    factors = _UNIT_FACTORS.get(spec.unit, {})
    if u in factors:
        return value * factors[u]
    # Unit we do not recognise: keep the number, let the caller flag it.
    return value


def parse_lab_text(text: str) -> tuple[dict[str, float], list[str]]:
    """Extract marker values from free text, a pasted line list, or a CSV.

    Returns ``(values, unrecognised_lines)``. Keys are :data:`KNOWN_MARKERS` keys;
    values are in each marker's canonical unit.
    """
    values: dict[str, float] = {}
    unrecognised: list[str] = []

    # A JSON object of already-structured values is accepted directly.
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
            for key, raw in obj.items():
                spec = KNOWN_MARKERS.get(str(key).strip().lower()) or _spec_for(str(key))
                if spec is not None:
                    values[spec.key] = float(raw)
            return values, []
        except (ValueError, TypeError):
            pass

    for raw_line in text.splitlines():
        line = raw_line.strip().strip('";')
        if not line:
            continue
        hit = _match_line(line)
        if hit is None:
            unrecognised.append(raw_line)
            continue
        spec, value, unit = hit
        values[spec.key] = _convert(spec, value, unit)
    return values, unrecognised


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LabMarker:
    """One parsed marker with its reference band and status."""

    key: str
    label: str
    unit: str
    value: float
    reference_low: float | None
    reference_high: float | None
    status: str  # "low" | "normal" | "high" | "unknown"
    note: str = ""


@dataclass(frozen=True, slots=True)
class LabFinding:
    """A dietary focus implied by one out-of-range marker."""

    marker: str
    label: str
    status: str
    message: str
    dietary_focus: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LabReport:
    """Outcome of :func:`analyze_lab_text`."""

    markers: list[LabMarker]
    findings: list[LabFinding]
    unrecognised_lines: list[str] = field(default_factory=list)
    disclaimer: str = (
        "These are dietary suggestions, not a medical diagnosis. Laboratory "
        "values must be interpreted by a qualified clinician in the context of "
        "the full report. Nothing you enter is stored."
    )

    @property
    def has_attention(self) -> bool:
        return any(f.status != "normal" for f in self.findings)


def _status(low: float | None, high: float | None, value: float) -> str:
    if low is not None and value < low:
        return "low"
    if high is not None and value > high:
        return "high"
    return "normal"


#: Which dietary focus flags an out-of-range marker raises.
_FOCUS: dict[tuple[str, str], tuple[str, ...]] = {
    ("hemoglobin", "low"): ("iron_focus", "vitamin_c"),
    ("ferritin", "low"): ("iron_focus", "vitamin_c"),
    ("fasting_glucose", "high"): ("glycemic_control",),
    ("hba1c", "high"): ("glycemic_control",),
    ("total_cholesterol", "high"): ("low_saturated_fat", "high_fibre"),
    ("ldl", "high"): ("low_saturated_fat", "high_fibre"),
    ("hdl", "low"): ("healthy_fats",),
    ("triglycerides", "high"): ("glycemic_control", "low_saturated_fat", "healthy_fats"),
    ("vitamin_d", "low"): ("vitamin_d_focus",),
    ("vitamin_b12", "low"): ("vitamin_b12_focus",),
    ("calcium", "low"): ("calcium_focus",),
}


def findings_for(markers: list[LabMarker]) -> list[LabFinding]:
    """Dietary findings for every out-of-range marker."""
    findings: list[LabFinding] = []
    for marker in markers:
        if marker.status == "normal":
            continue
        focus = _FOCUS.get((marker.key, marker.status), ())
        message = _message(marker)
        findings.append(
            LabFinding(
                marker=marker.key,
                label=marker.label,
                status=marker.status,
                message=message,
                dietary_focus=focus,
            )
        )
    return findings


def _message(marker: LabMarker) -> str:
    band = ""
    if marker.reference_low is not None and marker.reference_high is not None:
        band = f"reference {marker.reference_low:g}–{marker.reference_high:g} {marker.unit}"
    elif marker.reference_low is not None:
        band = f"reference ≥ {marker.reference_low:g} {marker.unit}"
    elif marker.reference_high is not None:
        band = f"reference ≤ {marker.reference_high:g} {marker.unit}"
    return (
        f"{marker.label} is {marker.value:g} {marker.unit} ({marker.status}; {band}). "
        f"{marker.note}"
    )


def analyze_lab_text(
    text: str, sex: Sex | str | None = None
) -> LabReport:
    """Parse and interpret lab text.

    ``sex`` only adjusts the haemoglobin reference lower bound (the values here are
    sex-neutral by default, so this is a light touch).
    """
    values, unrecognised = parse_lab_text(text)
    markers: list[LabMarker] = []
    for key, value in values.items():
        spec = KNOWN_MARKERS[key]
        low, high = spec.low, spec.high
        if key == "hemoglobin" and sex is not None and Sex(sex) is Sex.FEMALE:
            low = 12.0
        markers.append(
            LabMarker(
                key=spec.key,
                label=spec.label,
                unit=spec.unit,
                value=round(value, 3),
                reference_low=low,
                reference_high=high,
                status=_status(low, high, value),
                note=spec.note,
            )
        )
    markers.sort(key=lambda m: m.key)
    return LabReport(
        markers=markers,
        findings=findings_for(markers),
        unrecognised_lines=unrecognised,
    )
