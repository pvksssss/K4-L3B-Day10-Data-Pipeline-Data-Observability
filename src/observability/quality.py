from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import great_expectations as gx
import pandas as pd

from core.config import Settings


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def _parse_published_dates(series: pd.Series) -> pd.Series:
    """Parse publication dates as timezone-aware UTC timestamps."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def evaluate_freshness_sla(
    df: pd.DataFrame,
    settings: Settings,
) -> dict[str, Any]:
    """
    Check data freshness.

    A record is considered stale when age_days > 180 days.
    If more than 25% of records are stale, is_fresh=False.
    """
    total_rows = len(df)

    if total_rows == 0:
        return {
            "is_fresh": False,
            "total_rows": 0,
            "stale_rows": 0,
            "stale_fraction": 0.0,
            "threshold_days": settings.freshness_threshold_days,
            "max_stale_fraction": 0.25,
        }

    if "age_days" in df.columns:
        age_days = pd.to_numeric(df["age_days"], errors="coerce")
    elif "published" in df.columns:
        published_dates = _parse_published_dates(df["published"])
        now = pd.Timestamp.now(tz="UTC")
        age_days = (
            (now - published_dates).dt.total_seconds() / 86400
        )
    else:
        raise ValueError(
            "DataFrame must contain either 'age_days' or 'published'."
        )

    stale_mask = age_days > settings.freshness_threshold_days

    stale_rows = int(stale_mask.fillna(False).sum())
    invalid_age_rows = int(age_days.isna().sum())

    stale_fraction = stale_rows / total_rows

    is_fresh = (
        invalid_age_rows == 0
        and stale_fraction <= 0.25
    )

    return {
        "is_fresh": is_fresh,
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "stale_fraction": stale_fraction,
        "invalid_age_rows": invalid_age_rows,
        "threshold_days": settings.freshness_threshold_days,
        "max_stale_fraction": 0.25,
    }


def run_data_quality_checks(
    df: pd.DataFrame,
    settings: Settings,
    stage: str,
) -> dict[str, Any]:
    """
    Run the Great Expectations data-quality gate.

    Required expectations:
    1. Row count between 5 and 5000.
    2. paper_id, title and text_for_embedding are not null.
    3. paper_id is unique.
    4. summary length is at least 30 characters.

    Also evaluates freshness:
    - age_days > 180 is considered stale.
    - More than 25% stale records => is_fresh=False.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    required_columns = {
        "paper_id",
        "title",
        "summary",
        "text_for_embedding",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            "DataFrame is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    # ===============================================================
    # Great Expectations 1.x - Ephemeral Context
    # ===============================================================
    context = gx.get_context(mode="ephemeral")

    data_source = context.data_sources.add_pandas(
        name="papers_source"
    )

    data_asset = data_source.add_dataframe_asset(
        name="papers_asset"
    )

    batch_def = data_asset.add_batch_definition_whole_dataframe(
        "papers_batch"
    )

    batch = batch_def.get_batch(
        batch_parameters={"dataframe": df}
    )

    # ===============================================================
    # 1. Row count: 5 <= rows <= 5000
    # ===============================================================
    row_count_expectation = gx.expectations.ExpectTableRowCountToBeBetween(
        min_value=5,
        max_value=5000,
    )

    # ===============================================================
    # 2. Required columns must not contain null
    # ===============================================================
    not_null_expectations = [
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="paper_id"
        ),
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="title"
        ),
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="text_for_embedding"
        ),
    ]

    # ===============================================================
    # 3. paper_id must be unique
    # ===============================================================
    unique_expectation = (
        gx.expectations.ExpectColumnValuesToBeUnique(
            column="paper_id"
        )
    )

    # ===============================================================
    # 4. summary length >= 30
    # ===============================================================
    summary_length_expectation = (
        gx.expectations.ExpectColumnValueLengthsToBeBetween(
            column="summary",
            min_value=30,
        )
    )

    expectations = [
        row_count_expectation,
        *not_null_expectations,
        unique_expectation,
        summary_length_expectation,
    ]

    results: dict[str, Any] = {}

    for index, expectation in enumerate(expectations, start=1):
        result = batch.validate(expectation)

        results[f"expectation_{index}"] = {
            "success": bool(result.success),
            "expectation_type": expectation.expectation_type,
            "result": result.to_json_dict(),
        }

    gx_success = all(
        result["success"]
        for result in results.values()
    )

    # ===============================================================
    # Freshness SLA
    # ===============================================================
    freshness = evaluate_freshness_sla(
        df,
        settings,
    )

    # ===============================================================
    # Overall quality gate
    # ===============================================================
    success = gx_success and freshness["is_fresh"]

    report: dict[str, Any] = {
        "stage": stage,
        "generated_at": datetime.now(UTC).isoformat(),
        "success": success,
        "gx_success": gx_success,
        "freshness": freshness,
        "total_rows": len(df),
        "expectations": results,
    }

    # ===============================================================
    # Save report
    # ===============================================================
    output_path = (
        settings.paths.quality_dir
        / f"{stage}_quality_report.json"
    )

    _write_json(output_path, report)

    return report


def build_freshness_report(
    df: pd.DataFrame,
    settings: Settings,
    report_path,
) -> dict[str, Any]:
    """Build and save a publication-date freshness report."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    freshness = evaluate_freshness_sla(
        df,
        settings,
    )

    published_dates = _parse_published_dates(
        df["published"]
    ) if "published" in df.columns else pd.Series(dtype="datetime64[ns, UTC]")

    valid_dates = published_dates.dropna()

    if valid_dates.empty:
        report = {
            "latest_published": None,
            "oldest_published": None,
            **freshness,
        }
    else:
        report = {
            "latest_published": valid_dates.max().strftime(
                "%Y-%m-%d"
            ),
            "oldest_published": valid_dates.min().strftime(
                "%Y-%m-%d"
            ),
            **freshness,
        }

    _write_json(Path(report_path), report)

    return report