from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _parse_published_dates(series: pd.Series) -> pd.Series:
    """Parse publication dates as timezone-aware UTC timestamps."""
    return pd.to_datetime(series, errors="coerce", utc=True)


def run_data_quality_checks(
    df: pd.DataFrame,
    settings: Settings,
    report_name: str,
) -> dict[str, Any]:
    """Run data-quality checks and save the resulting JSON report.

    Checks:
    1. Row count.
    2. `paper_id` is not null and unique.
    3. `title` is not null.
    4. Summary length / empty summaries.
    5. Publication-date freshness.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    required_columns = {
        "paper_id",
        "title",
        "summary",
        "published",
    }

    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            "DataFrame is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    total_rows = len(df)

    # ---------------------------------------------------------------
    # 1. Row count
    # ---------------------------------------------------------------
    row_count_passed = total_rows > 0

    # ---------------------------------------------------------------
    # 2. paper_id not null and unique
    # ---------------------------------------------------------------
    paper_ids = df["paper_id"]

    null_paper_ids = int(paper_ids.isna().sum())

    non_null_ids = paper_ids.dropna().astype(str).str.strip()
    duplicate_paper_ids = int(non_null_ids.duplicated(keep=False).sum())

    paper_id_passed = (
        null_paper_ids == 0
        and duplicate_paper_ids == 0
    )

    # ---------------------------------------------------------------
    # 3. title not null / empty
    # ---------------------------------------------------------------
    titles = df["title"]

    null_titles = int(titles.isna().sum())
    empty_titles = int(
        titles.fillna("").astype(str).str.strip().eq("").sum()
    )

    title_passed = (
        null_titles == 0
        and empty_titles == 0
    )

    # ---------------------------------------------------------------
    # 4. Summary length
    # ---------------------------------------------------------------
    summaries = df["summary"]

    summary_text = summaries.fillna("").astype(str).str.strip()
    summary_lengths = summary_text.str.len()

    empty_summaries = int(summary_text.eq("").sum())

    # A very short summary is useful to flag separately, but does not
    # automatically fail the check.
    short_summaries = int(
        summary_lengths.between(1, 49).sum()
    )

    summary_passed = empty_summaries == 0

    # ---------------------------------------------------------------
    # 5. Freshness
    # ---------------------------------------------------------------
    published_dates = _parse_published_dates(df["published"])

    invalid_dates = int(published_dates.isna().sum())

    now = pd.Timestamp.now(tz="UTC")

    age_days = (
        (now - published_dates).dt.total_seconds() / 86400
    )

    stale_mask = (
        age_days > settings.freshness_threshold_days
    ).fillna(False)

    stale_rows = int(stale_mask.sum())

    freshness_passed = (
        invalid_dates == 0
        and stale_rows == 0
    )

    # ---------------------------------------------------------------
    # Overall result
    # ---------------------------------------------------------------
    passed = (
        row_count_passed
        and paper_id_passed
        and title_passed
        and summary_passed
        and freshness_passed
    )

    report: dict[str, Any] = {
        "report_name": report_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "total_rows": total_rows,
        "passed": passed,
        "checks": {
            "row_count": {
                "passed": row_count_passed,
                "value": total_rows,
            },
            "paper_id": {
                "passed": paper_id_passed,
                "null_rows": null_paper_ids,
                "duplicate_rows": duplicate_paper_ids,
                "unique_values": int(non_null_ids.nunique()),
            },
            "title": {
                "passed": title_passed,
                "null_rows": null_titles,
                "empty_rows": empty_titles,
            },
            "summary": {
                "passed": summary_passed,
                "empty_rows": empty_summaries,
                "short_rows": short_summaries,
                "min_length": (
                    int(summary_lengths.min())
                    if total_rows
                    else 0
                ),
                "max_length": (
                    int(summary_lengths.max())
                    if total_rows
                    else 0
                ),
                "average_length": (
                    float(summary_lengths.mean())
                    if total_rows
                    else 0.0
                ),
            },
            "freshness": {
                "passed": freshness_passed,
                "threshold_days": settings.freshness_threshold_days,
                "stale_rows": stale_rows,
                "invalid_date_rows": invalid_dates,
            },
        },
    }

    # Save under data/quality/.
    output_path = (
        settings.paths.quality_dir
        / f"{report_name}.json"
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

    if "published" not in df.columns:
        raise ValueError(
            "DataFrame must contain a 'published' column."
        )

    total_rows = len(df)

    published_dates = _parse_published_dates(
        df["published"]
    )

    valid_dates = published_dates.dropna()

    if valid_dates.empty:
        report = {
            "latest_published": None,
            "oldest_published": None,
            "stale_rows": 0,
            "total_rows": total_rows,
            "valid_date_rows": 0,
            "invalid_date_rows": total_rows,
            "freshness_threshold_days": (
                settings.freshness_threshold_days
            ),
            "is_fresh": False,
        }
    else:
        latest_published = valid_dates.max()
        oldest_published = valid_dates.min()

        now = pd.Timestamp.now(tz="UTC")

        age_days = (
            (now - published_dates).dt.total_seconds()
            / 86400
        )

        stale_rows = int(
            (
                age_days > settings.freshness_threshold_days
            )
            .fillna(False)
            .sum()
        )

        valid_date_rows = int(published_dates.notna().sum())
        invalid_date_rows = total_rows - valid_date_rows

        report = {
            "latest_published": latest_published.strftime(
                "%Y-%m-%d"
            ),
            "oldest_published": oldest_published.strftime(
                "%Y-%m-%d"
            ),
            "stale_rows": stale_rows,
            "total_rows": total_rows,
            "valid_date_rows": valid_date_rows,
            "invalid_date_rows": invalid_date_rows,
            "freshness_threshold_days": (
                settings.freshness_threshold_days
            ),
            "is_fresh": (
                total_rows > 0
                and valid_date_rows == total_rows
                and stale_rows == 0
            ),
        }

    _write_json(Path(report_path), report)

    return report
