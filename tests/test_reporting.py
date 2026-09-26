from __future__ import annotations

from observability.reporting import generate_phase1_report


def test_generate_phase1_report_contains_source_metrics_quality_and_freshness(tmp_path):
    report_path = tmp_path / "reports" / "phase1.md"
    source = {
        "source_api": "Crossref REST API",
        "raw_records": 12,
        "clean_records": 10,
        "raw_records_path": "data/raw/crossref_records.json",
        "clean_csv_path": "data/clean/papers_clean.csv",
        "clean_json_path": "data/clean/papers_clean.json",
        "embeddings_path": "data/embeddings/papers_embeddings.json",
        "test_set_path": "data/eval/test_set.json",
        "metrics_path": "data/results/baseline_metrics.json",
        "answers_path": "data/results/baseline_answers.json",
        "quality_path": "data/quality/baseline_quality_report.json",
        "freshness_path": "data/quality/freshness_report.json",
    }
    metrics = {
        "samples": 10,
        "retrieval_hit_rate": 0.8,
        "mean_token_f1": 0.675,
        "judge_accuracy": 0.7,
        "mean_judge_score": 3.4,
    }
    quality = {
        "success": False,
        "gx_success": True,
        "expectations": [
            {"expectation_type": "expect_column_values_to_be_unique", "column": "paper_id", "success": True},
            {"expectation_type": "expect_column_value_lengths_to_be_between", "column": "summary", "success": False},
        ],
    }
    freshness = {"stale_rows": 3, "total_rows": 10, "stale_ratio": 0.3, "is_fresh": False, "threshold_days": 180}

    generate_phase1_report(report_path, source, metrics, quality, freshness)

    report = report_path.read_text(encoding="utf-8")
    assert "Crossref REST API" in report
    assert "12" in report and "10" in report
    for path in ("crossref_records.json", "papers_clean.csv", "papers_clean.json", "papers_embeddings.json",
                 "test_set.json", "baseline_metrics.json", "baseline_answers.json",
                 "baseline_quality_report.json", "freshness_report.json"):
        assert path in report
    for label, value in (("retrieval_hit_rate", "0.800"), ("mean_token_f1", "0.675"),
                         ("judge_accuracy", "0.700"), ("mean_judge_score", "3.400")):
        assert label in report and value in report
    assert "expect_column_values_to_be_unique" in report
    assert "expect_column_value_lengths_to_be_between" in report
    assert "PASS" in report and "FAIL" in report
    assert "0.300" in report
    assert "TODO" not in report and "placeholder" not in report.lower()
