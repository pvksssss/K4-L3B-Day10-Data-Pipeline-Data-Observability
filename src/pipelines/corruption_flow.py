from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Run the 3-state data corruption, observability gate, and idempotent repair workflow."""
    settings = load_settings()
    paths = settings.paths

    # 1. Load or rebuild baseline
    if paths.clean_json.exists():
        clean_df = pd.DataFrame(read_json(paths.clean_json))
    else:
        records = fetch_source_records(settings)
        clean_df = build_clean_dataframe(records, now_utc())
        write_csv(clean_df, paths.clean_csv)
        write_json(paths.clean_json, clean_df.to_dict(orient="records"))

    if not paths.eval_testset.exists():
        build_test_set(clean_df, paths.eval_testset)

    if paths.baseline_metrics.exists():
        baseline_metrics = read_json(paths.baseline_metrics)
    else:
        baseline_index = LocalEmbeddingIndex.build(clean_df, settings, embeddings_output_path=paths.embeddings_json)
        baseline_eval = evaluate_pipeline(
            settings, baseline_index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers
        )
        baseline_metrics = baseline_eval.summary

    # 2. Corrupt clean dataset with 6 synthetic scenarios
    corrupted_df = corrupt_clean_dataframe(clean_df, paths.corruption_log)
    write_csv(corrupted_df, paths.corrupted_clean_csv)
    write_json(paths.corrupted_clean_json, corrupted_df.to_dict(orient="records"))

    # 3. Index and evaluate corrupted dataset (Measure Silent Failure)
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, embeddings_output_path=paths.corrupted_embeddings_json)
    corrupted_eval = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")

    # 4. Idempotent Repair from authoritative raw snapshot
    raw_records = load_raw_records(paths.raw_records_json)
    if not raw_records:
        raw_records = fetch_source_records(settings)
    repaired_df = build_clean_dataframe(raw_records, now_utc())
    write_csv(repaired_df, paths.repaired_clean_csv)
    write_json(paths.repaired_clean_json, repaired_df.to_dict(orient="records"))

    # 5. Index and evaluate repaired dataset (Measure Recovery)
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, embeddings_output_path=paths.repaired_embeddings_json)
    repaired_eval = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")

    # 6. Generate 3-state comparison report
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_eval.summary,
        repaired_metrics=repaired_eval.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_quality["freshness"],
        repaired_freshness=repaired_quality["freshness"],
    )

    print("\n" + "=" * 78)
    print(" 3-STATE DATA OBSERVABILITY & RECOVERY BENCHMARK RESULTS")
    print("=" * 78)
    print(f"{'Metric':<30} | {'Baseline':<12} | {'Corrupted':<12} | {'Repaired':<12}")
    print("-" * 78)
    print(f"{'Retrieval Hit Rate':<30} | {baseline_metrics['retrieval_hit_rate']:<12.3f} | {corrupted_eval.summary['retrieval_hit_rate']:<12.3f} | {repaired_eval.summary['retrieval_hit_rate']:<12.3f}")
    print(f"{'Mean Token F1':<30} | {baseline_metrics['mean_token_f1']:<12.3f} | {corrupted_eval.summary['mean_token_f1']:<12.3f} | {repaired_eval.summary['mean_token_f1']:<12.3f}")
    print(f"{'Judge Accuracy':<30} | {baseline_metrics['judge_accuracy']:<12.3f} | {corrupted_eval.summary['judge_accuracy']:<12.3f} | {repaired_eval.summary['judge_accuracy']:<12.3f}")
    print(f"{'Mean Judge Score':<30} | {baseline_metrics['mean_judge_score']:<12.3f} | {corrupted_eval.summary['mean_judge_score']:<12.3f} | {repaired_eval.summary['mean_judge_score']:<12.3f}")
    print(f"{'Quality Gate (GX 1.x)':<30} | {'PASS':<12} | {'FAIL' if not corrupted_quality['gx_success'] else 'PASS':<12} | {'PASS' if repaired_quality['gx_success'] else 'FAIL':<12}")
    print(f"{'Freshness SLA':<30} | {'PASS':<12} | {'FAIL' if not corrupted_quality['freshness']['is_fresh'] else 'PASS':<12} | {'PASS' if repaired_quality['freshness']['is_fresh'] else 'FAIL':<12}")
    print("=" * 78)
    print(f"Report generated at: {paths.comparison_report}\n")
