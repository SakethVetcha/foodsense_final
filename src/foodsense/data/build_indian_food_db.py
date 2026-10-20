"""Build ``data/processed/indian_food_db.{parquet,sqlite}`` from IFCT 2017.

    python -m foodsense.data.build_indian_food_db            # build (fetch CSV if absent)
    python -m foodsense.data.build_indian_food_db --stats    # rebuild and print the report
    python -m foodsense.data.build_indian_food_db --download # only fetch the IFCT CSV

The output schema is byte-identical to the USDA database's, so ``FoodDB`` and
everything downstream load it without modification.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from foodsense import INDIA_FOOD_DB_PARQUET, INDIA_FOOD_DB_SQLITE, SEED
from foodsense.data.indian_food import (
    IFCT_CSV,
    IFCT_URL,
    IndianBuildReport,
    curate_indian_food_db,
)
from foodsense.schemas import NUTRIENTS

__all__ = ["download_ifct", "main", "write_outputs"]


def download_ifct(force: bool = False) -> Path:
    """Fetch the machine-readable IFCT 2017 table into ``data/raw/ifct/``."""
    if IFCT_CSV.exists() and not force:
        print(f"  cached   {IFCT_CSV} ({IFCT_CSV.stat().st_size / 1e6:.2f} MB)")
        return IFCT_CSV
    IFCT_CSV.parent.mkdir(parents=True, exist_ok=True)
    print(f"  download {IFCT_CSV.name} <- {IFCT_URL}")
    try:
        req = urllib.request.Request(IFCT_URL, headers={"User-Agent": "foodsense/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r, IFCT_CSV.open("wb") as fh:
            fh.write(r.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemExit(
            f"\nCould not download the IFCT table: {exc}\n"
            f"Download it manually from {IFCT_URL} to {IFCT_CSV} and re-run.\n"
            f"See data/README.md."
        ) from exc
    print(f"           {IFCT_CSV.stat().st_size / 1e6:.2f} MB")
    return IFCT_CSV


def write_outputs(db: pd.DataFrame, report: IndianBuildReport) -> None:
    INDIA_FOOD_DB_SQLITE.parent.mkdir(parents=True, exist_ok=True)

    if INDIA_FOOD_DB_SQLITE.exists():
        INDIA_FOOD_DB_SQLITE.unlink()
    with sqlite3.connect(INDIA_FOOD_DB_SQLITE) as conn:
        db.to_sql("foods", conn, index=False)
        conn.execute("CREATE UNIQUE INDEX idx_foods_fdc_id ON foods(fdc_id)")
        conn.execute("CREATE INDEX idx_foods_category ON foods(category)")
        conn.execute("CREATE TABLE build_info (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO build_info (key, value) VALUES (?, ?)",
            [
                ("built_at", datetime.now(UTC).isoformat(timespec="seconds")),
                ("seed", str(SEED)),
                ("n_foods", str(report.n_final)),
                ("source", report.source),
                ("nutrients", json.dumps(list(NUTRIENTS))),
            ],
        )
        conn.commit()

    db.to_parquet(INDIA_FOOD_DB_PARQUET, index=False, compression="zstd")

    print("\nWrote:")
    print(f"  {INDIA_FOOD_DB_SQLITE}   {INDIA_FOOD_DB_SQLITE.stat().st_size / 1e6:.2f} MB")
    print(f"  {INDIA_FOOD_DB_PARQUET}  {INDIA_FOOD_DB_PARQUET.stat().st_size / 1e6:.2f} MB")


def print_report(db: pd.DataFrame, report: IndianBuildReport) -> None:
    print("\n" + "=" * 72)
    print("INDIAN FOOD DATABASE BUILD REPORT (IFCT 2017)")
    print("=" * 72)
    print(f"Source          : {report.source}")
    print(f"IFCT ingredient rows : {report.n_ifct_rows}")
    print(f"Composite dishes     : {report.n_dishes}")
    print(f"FINAL FOODS          : {report.n_final}")

    print("\n--- category histogram ---")
    for name, count in report.category_counts.items():
        print(f"  {name:<16} {count:>5}  {'#' * max(1, round(count / 4))}")

    print("\n--- meal-slot coverage ---")
    for name, count in report.slot_counts.items():
        print(f"  {name:<16} {count:>5}")

    print("\n--- diet-class counts ---")
    for name, count in report.diet_counts.items():
        print(f"  {name:<16} {count:>5}")

    print("\n--- nutrient coverage (share of foods with a non-zero value) ---")
    for nutrient, share in report.nutrient_coverage.items():
        print(f"  {nutrient:<26} {share * 100:5.1f}%")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stats", action="store_true", help="print the full build report")
    parser.add_argument("--download", action="store_true", help="fetch the IFCT CSV and exit")
    parser.add_argument("--force-download", action="store_true", help="re-fetch the IFCT CSV")
    args = parser.parse_args(argv)

    download_ifct(force=args.force_download)
    if args.download:
        return 0

    print("\nComposing dishes and curating the Indian food table...")
    db, report = curate_indian_food_db()
    write_outputs(db, report)
    if args.stats:
        print_report(db, report)
    else:
        print(f"\n{report.n_final} foods across {len(report.category_counts)} categories.")
        print("Run with --stats for the full report.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
