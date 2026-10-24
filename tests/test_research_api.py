"""Tests for research evaluation, publication figure generation, and export endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from foodsense.api.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestResearchEndpoints:
    def test_get_research_figures(self, client: TestClient):
        res = client.get("/api/research/figures")
        assert res.status_code == 200
        figures = res.json()
        assert isinstance(figures, list)
        assert len(figures) >= 5
        for fig in figures:
            assert "figure_id" in fig
            assert "number" in fig
            assert "title" in fig
            assert "caption" in fig
            assert "png_path" in fig
            assert "svg_path" in fig
            assert "csv_path" in fig

    def test_get_research_eval_data(self, client: TestClient):
        res = client.get("/api/research/eval-data")
        assert res.status_code == 200
        data = res.json()
        assert "cf_comparison" in data
        assert "lambda_sweep" in data
        assert "surrogate_boundary" in data
        assert "verification_eval" in data
        assert len(data["cf_comparison"]) > 0
        assert len(data["lambda_sweep"]) > 0
        assert data["surrogate_boundary"].get("target") == 0.7

    def test_download_figure_assets(self, client: TestClient):
        # Test download of PNG
        png_res = client.get("/api/research/download-figure/fig1_cf_method_comparison.png")
        assert png_res.status_code == 200
        assert png_res.headers["content-type"] == "image/png"
        assert len(png_res.content) > 1000

        # Test download of SVG
        svg_res = client.get("/api/research/download-figure/fig1_cf_method_comparison.svg")
        assert svg_res.status_code == 200
        assert "svg" in svg_res.headers["content-type"]
        assert len(svg_res.content) > 500

        # Test download of CSV
        csv_res = client.get("/api/research/download-figure/fig1_cf_method_comparison.csv")
        assert csv_res.status_code == 200
        assert "csv" in csv_res.headers["content-type"]
        assert b"FoodSense" in csv_res.content

        # Test download of ZIP package
        zip_res = client.get("/api/research/download-figure/foodsense_publication_figures.zip")
        assert zip_res.status_code == 200
        assert zip_res.headers["content-type"] == "application/zip"
        assert len(zip_res.content) > 5000

    def test_download_figure_security_path_traversal(self, client: TestClient):
        res = client.get("/api/research/download-figure/..%2F..%2Fsecret.txt")
        assert res.status_code in (400, 404)

        res404 = client.get("/api/research/download-figure/non_existent_file.png")
        assert res404.status_code == 404

    def test_post_generate_figures(self, client: TestClient):
        res = client.post("/api/research/generate-figures", json={})
        assert res.status_code == 200
        figures = res.json()
        assert isinstance(figures, list)
        assert len(figures) >= 5
