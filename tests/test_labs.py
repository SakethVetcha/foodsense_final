"""Tests for the optional lab-report parser (``foodsense.labs``)."""

from __future__ import annotations

from foodsense.labs import KNOWN_MARKERS, analyze_lab_text, parse_lab_text

SAMPLE = """Hemoglobin: 10.2 g/dL
Fasting glucose 112 mg/dL
HbA1c 6.1 %
Total Cholesterol - 215 mg/dL
LDL 138
HDL: 36 mg/dL
Triglycerides 190 mg/dL
Vitamin D 18 ng/mL
Vitamin B12 180 pg/mL
Serum calcium 9.1 mg/dL
"""


class TestParsing:
    def test_reads_labelled_values(self):
        values, _ = parse_lab_text(SAMPLE)
        assert values["hemoglobin"] == 10.2
        assert values["fasting_glucose"] == 112.0
        assert values["hba1c"] == 6.1
        assert values["ldl"] == 138.0

    def test_distinguishes_total_from_ldl_cholesterol(self):
        values, _ = parse_lab_text(SAMPLE)
        assert values["total_cholesterol"] == 215.0
        assert values["ldl"] == 138.0

    def test_reads_a_value_glued_to_a_digit_token(self):
        """\"Vitamin B12 180\" must not be read as B1 = 2."""
        values, _ = parse_lab_text(SAMPLE)
        assert values["vitamin_b12"] == 180.0

    def test_accepts_a_json_object(self):
        values, _ = parse_lab_text('{"hemoglobin": 9.8, "vitamin_d": 64}')
        assert values == {"hemoglobin": 9.8, "vitamin_d": 64.0}

    def test_accepts_a_csv_style_paste(self):
        values, _ = parse_lab_text("hemoglobin,13.5\nglucose,88")
        assert values["hemoglobin"] == 13.5
        assert values["fasting_glucose"] == 88.0

    def test_unrecognised_lines_are_reported_not_silently_dropped(self):
        _, unrecognised = parse_lab_text("Hemoglobin 13\nSome Random Test 42")
        assert any("Some Random Test" in line for line in unrecognised)

    def test_empty_text_is_not_an_error(self):
        report = analyze_lab_text("")
        assert report.markers == []
        assert report.findings == []


class TestFindings:
    def test_flags_out_of_range_markers(self):
        report = analyze_lab_text(SAMPLE, sex="female")
        by_key = {m.key: m for m in report.markers}
        assert by_key["hemoglobin"].status == "low"
        assert by_key["fasting_glucose"].status == "high"
        assert by_key["vitamin_d"].status == "low"
        assert by_key["calcium"].status == "normal"

    def test_findings_carry_dietary_focus(self):
        report = analyze_lab_text(SAMPLE, sex="female")
        focus = {f for finding in report.findings for f in finding.dietary_focus}
        assert "iron_focus" in focus
        assert "glycemic_control" in focus
        assert "low_saturated_fat" in focus

    def test_normal_values_produce_no_findings(self):
        report = analyze_lab_text("Hemoglobin 14\nglucose 85\nVitamin D 45")
        assert report.findings == []
        assert report.has_attention is False

    def test_every_finding_is_phrased_as_advisory(self):
        report = analyze_lab_text(SAMPLE)
        assert "not a medical diagnosis" in report.disclaimer


def test_marker_catalogue_is_well_formed():
    for key, spec in KNOWN_MARKERS.items():
        assert spec.key == key
        assert spec.aliases
        assert spec.unit
