from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


def _status(success: bool) -> str:
    return "PASS" if success else "FAIL"


def _metric(value: Any) -> str:
    return f"{float(value):.3f}"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline source, evaluation, quality, and freshness evidence."""
    lines = [
        "# Phase-one baseline report",
        "",
        "## Source and artifacts",
        "",
        f"- Source: {source_summary['source_api']}",
        f"- Raw records: {source_summary['raw_records']}",
        f"- Clean records: {source_summary['clean_records']}",
    ]
    for key in (
        "raw_records_path", "clean_csv_path", "clean_json_path", "embeddings_path",
        "test_set_path", "metrics_path", "answers_path", "quality_path", "freshness_path",
    ):
        if key in source_summary:
            lines.append(f"- {key}: `{source_summary[key]}`")

    lines.extend(["", "## Baseline evaluation", "", f"- Samples: {metrics['samples']}"])
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"):
        lines.append(f"- {key}: {_metric(metrics[key])}")

    lines.extend([
        "", "## Data quality", "",
        f"- Overall: {_status(quality['success'])}",
        f"- Great Expectations: {_status(quality['gx_success'])}",
    ])
    for expectation in quality["expectations"]:
        column = f" ({expectation['column']})" if expectation.get("column") else ""
        lines.append(f"- {expectation['expectation_type']}{column}: {_status(expectation['success'])}")

    lines.extend([
        "", "## Freshness", "",
        f"- Status: {_status(freshness['is_fresh'])}",
        f"- Stale rows: {freshness['stale_rows']} / {freshness['total_rows']}",
        f"- Stale ratio: {_metric(freshness['stale_ratio'])}",
        f"- Threshold days: {freshness['threshold_days']}",
    ])
    for key in ("oldest_published", "latest_published"):
        if freshness.get(key) is not None:
            lines.append(f"- {key}: {freshness[key]}")
    write_text(Path(report_path), "\n".join(lines) + "\n")


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
    """TODO(student): viet markdown report so sanh baseline/corrupted/repaired."""
    raise NotImplementedError("Student task: implement corruption comparison report.")
