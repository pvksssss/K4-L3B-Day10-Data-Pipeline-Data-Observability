from __future__ import annotations

from pathlib import Path
from typing import Any


def _format_value(value: Any) -> str:
    """Format a value safely for Markdown."""
    if isinstance(value, bool):
        return "Yes" if value else "No"

    if value is None:
        return "N/A"

    if isinstance(value, float):
        return f"{value:.4f}"

    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)

    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {_format_value(item)}"
            for key, item in value.items()
        )

    return str(value)


def _write_report(report_path, content: str) -> None:
    """Create parent directory and write Markdown report."""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        content,
        encoding="utf-8",
    )


def _dict_to_markdown(
    data: dict[str, Any],
    *,
    level: int = 3,
) -> list[str]:
    """Convert a dictionary into readable Markdown sections."""
    lines: list[str] = []

    heading = "#" * level

    for key, value in data.items():
        label = str(key).replace("_", " ").title()

        if isinstance(value, dict):
            lines.append(f"{heading} {label}")
            lines.append("")

            for child_key, child_value in value.items():
                child_label = str(child_key).replace("_", " ").title()

                if isinstance(child_value, dict):
                    lines.append(
                        f"- **{child_label}:** "
                        f"{_format_value(child_value)}"
                    )
                else:
                    lines.append(
                        f"- **{child_label}:** "
                        f"{_format_value(child_value)}"
                    )

            lines.append("")
        else:
            lines.append(
                f"- **{label}:** {_format_value(value)}"
            )

    return lines


def _metric_rows(
    metrics: dict[str, Any],
    prefix: str = "",
) -> list[tuple[str, Any]]:
    """Flatten scalar metrics for a Markdown table."""
    rows: list[tuple[str, Any]] = []

    for key, value in metrics.items():
        name = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            rows.extend(
                _metric_rows(
                    value,
                    prefix=name,
                )
            )
        elif isinstance(value, (list, tuple, set)):
            rows.append((name, _format_value(value)))
        else:
            rows.append((name, value))

    return rows


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Generate the Markdown report for the baseline phase.

    The report summarizes:
    - source information,
    - retrieval/evaluation metrics,
    - data quality checks,
    - freshness status.
    """
    lines: list[str] = [
        "# Phase 1 Report",
        "",
        "## Overview",
        "",
        "This report summarizes the baseline data ingestion, "
        "retrieval/evaluation metrics, data quality, and freshness.",
        "",
        "## 1. Source Summary",
        "",
    ]

    lines.extend(
        _dict_to_markdown(
            source_summary,
            level=3,
        )
    )

    lines.extend(
        [
            "## 2. Retrieval and Evaluation Metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )

    for name, value in _metric_rows(metrics):
        lines.append(
            f"| `{name}` | {_format_value(value)} |"
        )

    lines.extend(
        [
            "",
            "## 3. Data Quality",
            "",
        ]
    )

    lines.extend(
        _dict_to_markdown(
            quality,
            level=3,
        )
    )

    lines.extend(
        [
            "## 4. Freshness",
            "",
        ]
    )

    lines.extend(
        _dict_to_markdown(
            freshness,
            level=3,
        )
    )

    lines.extend(
        [
            "## Conclusion",
            "",
            (
                "The baseline report records the source characteristics, "
                "evaluation metrics, data-quality status, and publication "
                "freshness used as the reference point for later experiments."
            ),
            "",
        ]
    )

    _write_report(
        report_path,
        "\n".join(lines),
    )


def _build_comparison_rows(
    baseline: dict[str, Any],
    corrupted: dict[str, Any],
    repaired: dict[str, Any],
) -> list[tuple[str, Any, Any, Any]]:
    """Build comparable rows from three metric dictionaries."""
    baseline_rows = dict(_metric_rows(baseline))
    corrupted_rows = dict(_metric_rows(corrupted))
    repaired_rows = dict(_metric_rows(repaired))

    keys = list(
        dict.fromkeys(
            [
                *baseline_rows.keys(),
                *corrupted_rows.keys(),
                *repaired_rows.keys(),
            ]
        )
    )

    return [
        (
            key,
            baseline_rows.get(key),
            corrupted_rows.get(key),
            repaired_rows.get(key),
        )
        for key in keys
    ]


def _freshness_status(data: dict[str, Any]) -> str:
    if "is_fresh" in data:
        return _format_value(data["is_fresh"])

    return "N/A"


def _quality_status(data: dict[str, Any]) -> str:
    if "passed" in data:
        return _format_value(data["passed"])

    return "N/A"


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Generate a Markdown comparison of baseline/corrupted/repaired data."""
    lines: list[str] = [
        "# Data Corruption and Repair Report",
        "",
        "## Overview",
        "",
        "This report compares evaluation metrics and data-quality "
        "signals across the corrupted and repaired datasets.",
        "",
        "## 1. Metrics Comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired |",
        "|---|---:|---:|---:|",
    ]

    for name, baseline, corrupted, repaired in _build_comparison_rows(
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
    ):
        lines.append(
            "| "
            f"`{name}` | "
            f"{_format_value(baseline)} | "
            f"{_format_value(corrupted)} | "
            f"{_format_value(repaired)} |"
        )

    lines.extend(
        [
            "",
            "## 2. Data Quality Comparison",
            "",
            "| Check | Corrupted | Repaired |",
            "|---|---:|---:|",
            (
                "| Overall passed | "
                f"{_quality_status(corrupted_quality)} | "
                f"{_quality_status(repaired_quality)} |"
            ),
        ]
    )

    corrupted_checks = corrupted_quality.get("checks", {})
    repaired_checks = repaired_quality.get("checks", {})

    check_names = list(
        dict.fromkeys(
            [
                *corrupted_checks.keys(),
                *repaired_checks.keys(),
            ]
        )
    )

    for check_name in check_names:
        corrupted_check = corrupted_checks.get(check_name, {})
        repaired_check = repaired_checks.get(check_name, {})

        if isinstance(corrupted_check, dict):
            corrupted_status = corrupted_check.get(
                "passed",
                "N/A",
            )
        else:
            corrupted_status = corrupted_check

        if isinstance(repaired_check, dict):
            repaired_status = repaired_check.get(
                "passed",
                "N/A",
            )
        else:
            repaired_status = repaired_check

        label = str(check_name).replace("_", " ").title()

        lines.append(
            f"| {label} | "
            f"{_format_value(corrupted_status)} | "
            f"{_format_value(repaired_status)} |"
        )

    lines.extend(
        [
            "",
            "## 3. Freshness Comparison",
            "",
            "| Metric | Corrupted | Repaired |",
            "|---|---:|---:|",
            (
                "| Latest published | "
                f"{_format_value(corrupted_freshness.get('latest_published'))} | "
                f"{_format_value(repaired_freshness.get('latest_published'))} |"
            ),
            (
                "| Oldest published | "
                f"{_format_value(corrupted_freshness.get('oldest_published'))} | "
                f"{_format_value(repaired_freshness.get('oldest_published'))} |"
            ),
            (
                "| Stale rows | "
                f"{_format_value(corrupted_freshness.get('stale_rows'))} | "
                f"{_format_value(repaired_freshness.get('stale_rows'))} |"
            ),
            (
                "| Total rows | "
                f"{_format_value(corrupted_freshness.get('total_rows'))} | "
                f"{_format_value(repaired_freshness.get('total_rows'))} |"
            ),
            (
                "| Is fresh | "
                f"{_freshness_status(corrupted_freshness)} | "
                f"{_freshness_status(repaired_freshness)} |"
            ),
            "",
            "## 4. Interpretation",
            "",
            (
                "The corrupted dataset is evaluated against the same "
                "quality and freshness checks as the repaired dataset. "
                "The tables above expose changes in retrieval/evaluation "
                "metrics and data-quality indicators without assuming "
                "that every metric should move in the same direction."
            ),
            "",
        ]
    )

    _write_report(
        report_path,
        "\n".join(lines),
    )
