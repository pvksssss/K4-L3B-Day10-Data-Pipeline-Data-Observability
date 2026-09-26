from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Build and report the phase-one baseline from the configured source."""
    settings = load_settings()
    paths = settings.paths
    records = fetch_source_records(settings)
    if not records:
        raise ValueError("Phase-one source has no usable records")

    clean = build_clean_dataframe(records, now_utc())
    if clean.empty:
        raise ValueError("Phase-one cleaning produced no usable records")
    write_csv(clean, paths.clean_csv)
    write_json(paths.clean_json, clean.to_dict(orient="records"))

    index = LocalEmbeddingIndex.build(clean, settings, embeddings_output_path=paths.embeddings_json)
    if settings.refresh_test_set or not paths.eval_testset.exists():
        build_test_set(clean, paths.eval_testset)
    evaluation = evaluate_pipeline(
        settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers
    )
    quality = run_data_quality_checks(clean, settings, "baseline")
    freshness = quality["freshness"]

    def relative(path):
        return path.relative_to(paths.project_dir).as_posix()

    source_summary = {
        "source_api": settings.source_api,
        "raw_records": len(records),
        "clean_records": len(clean),
        "raw_records_path": relative(paths.raw_records_json),
        "clean_csv_path": relative(paths.clean_csv),
        "clean_json_path": relative(paths.clean_json),
        "embeddings_path": relative(paths.embeddings_json),
        "test_set_path": relative(paths.eval_testset),
        "metrics_path": relative(paths.baseline_metrics),
        "answers_path": relative(paths.baseline_answers),
        "quality_path": relative(paths.baseline_quality_report),
        "freshness_path": relative(paths.freshness_report),
    }
    generate_phase1_report(paths.baseline_report, source_summary, evaluation.summary, quality, freshness)
    print(
        f"Phase one: {len(records)} raw, {len(clean)} clean, "
        f"{evaluation.summary['samples']} evaluated; quality="
        f"{'PASS' if quality['success'] else 'FAIL'}; report={paths.baseline_report}"
    )
