from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd

from core.config import load_settings
from observability.quality import build_freshness_report, run_data_quality_checks


def _settings(tmp_path):
    return replace(load_settings(tmp_path), freshness_threshold_days=180)


def _papers(ages):
    return pd.DataFrame(
        {
            "paper_id": [f"10.1234/{index}" for index in range(len(ages))],
            "title": [f"Paper {index}" for index in range(len(ages))],
            "summary": ["A sufficiently detailed paper summary." for _ in ages],
            "published": [f"2026-09-{20 + index:02d}" for index in range(len(ages))],
            "age_days": ages,
        }
    )


def test_freshness_passes_at_twenty_five_percent_stale(tmp_path):
    settings = _settings(tmp_path)
    report_path = tmp_path / "freshness.json"

    report = build_freshness_report(_papers([180, 181, 0, 1]), settings, report_path)

    assert report["latest_published"] == "2026-09-23"
    assert report["oldest_published"] == "2026-09-20"
    assert report["threshold_days"] == 180
    assert report["stale_rows"] == 1
    assert report["total_rows"] == 4
    assert report["stale_ratio"] == 0.25
    assert report["is_fresh"] is True
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_freshness_fails_above_twenty_five_percent_stale(tmp_path):
    report = build_freshness_report(
        _papers([181, 182, 180, 0]), _settings(tmp_path), tmp_path / "freshness.json"
    )

    assert report["stale_rows"] == 2
    assert report["stale_ratio"] == 0.5
    assert report["is_fresh"] is False


def test_freshness_handles_empty_dataframe(tmp_path):
    report_path = tmp_path / "freshness.json"

    report = build_freshness_report(_papers([]), _settings(tmp_path), report_path)

    assert report["latest_published"] is None
    assert report["oldest_published"] is None
    assert report["stale_rows"] == 0
    assert report["total_rows"] == 0
    assert report["stale_ratio"] == 0.0
    assert report["is_fresh"] is False
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_quality_gate_passes_valid_dataframe_and_writes_report(tmp_path):
    settings = _settings(tmp_path)

    report = run_data_quality_checks(_papers([0, 180]), settings, "baseline")

    checks = {(item["expectation_type"], item.get("column")): item["success"] for item in report["expectations"]}
    assert checks == {
        ("expect_table_row_count_to_be_between", None): True,
        ("expect_column_values_to_not_be_null", "paper_id"): True,
        ("expect_column_values_to_be_unique", "paper_id"): True,
        ("expect_column_values_to_not_be_null", "title"): True,
        ("expect_column_value_lengths_to_be_between", "summary"): True,
    }
    assert report["gx_success"] is True
    assert report["freshness"]["is_fresh"] is True
    assert report["success"] is True
    assert json.loads(settings.paths.baseline_quality_report.read_text(encoding="utf-8")) == report
    assert json.loads(settings.paths.freshness_report.read_text(encoding="utf-8")) == report["freshness"]


def test_quality_gate_fails_duplicate_and_short_summary(tmp_path):
    settings = _settings(tmp_path)
    df = _papers([0, 1])
    df.loc[1, "paper_id"] = df.loc[0, "paper_id"]
    df.loc[1, "summary"] = "Too short"

    report = run_data_quality_checks(df, settings, "corrupted")

    checks = {(item["expectation_type"], item.get("column")): item["success"] for item in report["expectations"]}
    assert checks[("expect_column_values_to_be_unique", "paper_id")] is False
    assert checks[("expect_column_value_lengths_to_be_between", "summary")] is False
    assert checks[("expect_table_row_count_to_be_between", None)] is True
    assert report["gx_success"] is False
    assert report["freshness"]["is_fresh"] is True
    assert report["success"] is False
    assert json.loads(settings.paths.corrupted_quality_report.read_text(encoding="utf-8")) == report


def test_quality_report_is_json_serializable(tmp_path):
    settings = _settings(tmp_path)

    report = run_data_quality_checks(_papers([0]), settings, "repaired")

    assert json.loads(json.dumps(report)) == report
    assert json.loads((settings.paths.quality_dir / "repaired_quality_report.json").read_text(encoding="utf-8")) == report
