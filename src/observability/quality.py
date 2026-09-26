from __future__ import annotations

from typing import Any
from pathlib import Path

import pandas as pd
import great_expectations as gx

from core.config import Settings
from core.utils import safe_slug, write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Validate the complete dataframe with GX and the freshness gate."""
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas("papers")
    data_asset = data_source.add_dataframe_asset(name="normalized_papers")
    batch_definition = data_asset.add_batch_definition_whole_dataframe("all_papers")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

    expectations = [
        gx.expectations.ExpectTableRowCountToBeBetween(min_value=1, max_value=settings.max_results),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="paper_id"),
        gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"),
        gx.expectations.ExpectColumnValuesToNotBeNull(column="title"),
        gx.expectations.ExpectColumnValueLengthsToBeBetween(
            column="summary", min_value=20, max_value=20_000
        ),
    ]
    checks = []
    for expectation in expectations:
        result = batch.validate(expectation)
        check = {
            "expectation_type": str(result.expectation_config.type),
            "success": bool(result.success),
        }
        if hasattr(expectation, "column"):
            check["column"] = str(expectation.column)
        if "observed_value" in result.result:
            check["observed_value"] = int(result.result["observed_value"])
        if "unexpected_count" in result.result:
            check["unexpected_count"] = int(result.result["unexpected_count"])
        checks.append(check)

    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)
    gx_success = all(check["success"] for check in checks)
    report = {
        "report_name": report_name,
        "success": bool(gx_success and freshness["is_fresh"]),
        "gx_success": bool(gx_success),
        "expectations": checks,
        "freshness": freshness,
    }
    if report_name == "baseline":
        report_path = settings.paths.baseline_quality_report
    elif report_name == "corrupted":
        report_path = settings.paths.corrupted_quality_report
    else:
        report_path = settings.paths.quality_dir / f"{safe_slug(report_name)}_quality_report.json"
    write_json(report_path, report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarize the normalized dates and age-based freshness gate."""
    total_rows = int(len(df))
    stale_rows = int((pd.to_numeric(df["age_days"]) > settings.freshness_threshold_days).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 0.0
    published = pd.to_datetime(df["published"], errors="coerce")
    latest = published.max()
    oldest = published.min()
    report = {
        "latest_published": None if pd.isna(latest) else latest.date().isoformat(),
        "oldest_published": None if pd.isna(oldest) else oldest.date().isoformat(),
        "threshold_days": int(settings.freshness_threshold_days),
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": float(stale_ratio),
        "is_fresh": bool(total_rows and stale_ratio <= 0.25),
    }
    write_json(Path(report_path), report)
    return report
