from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from core.config import load_settings
from core.utils import write_csv, write_text
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from observability.quality import build_freshness_report, run_data_quality_checks
from retrieval.index import LocalEmbeddingIndex


def _load_or_build_test_set(df: pd.DataFrame, settings):
    testset_path = settings.paths.eval_testset

    if settings.refresh_test_set or not testset_path.exists():
        return build_test_set(df, testset_path)

    import json

    return json.loads(testset_path.read_text(encoding="utf-8"))


def _build_report(
    settings,
    row_count: int,
    eval_count: int,
    metrics: dict,
    quality: dict,
    freshness_report: dict,
) -> str:
    generated_at = datetime.now(UTC).isoformat()

    ragas = metrics.get("ragas", {})
    if isinstance(ragas, dict) and "skipped" in ragas:
        ragas_status = "Skipped"
    elif isinstance(ragas, dict) and "error" in ragas:
        ragas_status = f"Error: {ragas['error']}"
    else:
        ragas_status = "Completed"

    quality_status = "PASS" if quality["success"] else "FAIL"
    gx_status = "PASS" if quality["gx_success"] else "FAIL"
    freshness_status = "PASS" if quality["freshness"]["is_fresh"] else "FAIL"

    lines = [
        "# Phase 1 — Baseline RAG Pipeline",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "## 1. Pipeline overview",
        "",
        "The baseline pipeline performs:",
        "",
        "1. Load raw Crossref records.",
        "2. Clean and normalize paper metadata.",
        "3. Save clean CSV/JSON artifacts.",
        "4. Build a persistent Chroma embedding index.",
        "5. Build or load the evaluation set.",
        "6. Evaluate baseline retrieval and answer quality.",
        "7. Run Great Expectations data-quality checks.",
        "8. Evaluate freshness SLA.",
        "",
        "## 2. Dataset",
        "",
        f"- Clean rows: **{row_count}**",
        f"- Evaluation questions: **{eval_count}**",
        "",
        "## 3. Baseline evaluation",
        "",
        f"- Retrieval Hit Rate: **{metrics['retrieval_hit_rate']:.4f}**",
        f"- Mean Token F1: **{metrics['mean_token_f1']:.4f}**",
        f"- Judge Accuracy: **{metrics['judge_accuracy']:.4f}**",
        f"- Mean Judge Score: **{metrics['mean_judge_score']:.4f} / 5**",
        f"- Ragas: **{ragas_status}**",
        "",
        "## 4. Data Quality Gate",
        "",
        f"- Overall Quality Gate: **{quality_status}**",
        f"- Great Expectations: **{gx_status}**",
        f"- Freshness: **{freshness_status}**",
        f"- Total rows checked: **{quality['total_rows']}**",
        f"- Stale rows: **{quality['freshness']['stale_rows']}**",
        f"- Stale fraction: **{quality['freshness']['stale_fraction']:.2%}**",
        f"- Freshness threshold: **{quality['freshness']['threshold_days']} days**",
        f"- Maximum allowed stale fraction: **{quality['freshness']['max_stale_fraction']:.0%}**",
        "",
        "## 5. Freshness report",
        "",
        f"- Latest published: **{freshness_report.get('latest_published')}**",
        f"- Oldest published: **{freshness_report.get('oldest_published')}**",
        f"- Freshness SLA: **{'PASS' if freshness_report.get('is_fresh') else 'FAIL'}**",
        f"- Stale rows: **{freshness_report.get('stale_rows', 0)}**",
        f"- Total rows: **{freshness_report.get('total_rows', 0)}**",
        "",
        "## 6. Output artifacts",
        "",
        f"- Clean CSV: `{settings.paths.clean_csv}`",
        f"- Clean JSON: `{settings.paths.clean_json}`",
        f"- Embedding manifest: `{settings.paths.embeddings_json}`",
        f"- Evaluation set: `{settings.paths.eval_testset}`",
        f"- Baseline metrics: `{settings.paths.baseline_metrics}`",
        f"- Baseline answers: `{settings.paths.baseline_answers}`",
        f"- Baseline quality report: `{settings.paths.baseline_quality_report}`",
        f"- Freshness report: `{settings.paths.freshness_report}`",
        f"- Phase 1 report: `{settings.paths.baseline_report}`",
        "",
        "## 7. Conclusion",
        "",
        (
            "Baseline pipeline completed successfully."
            if quality["success"]
            else "Baseline pipeline completed, but the data-quality gate failed."
        ),
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    """Build and evaluate the Phase 1 baseline RAG pipeline."""

    settings = load_settings()

    print("=" * 70)
    print("PHASE 1 — BASELINE RAG PIPELINE")
    print("=" * 70)

    # 1. Load raw records
    print("\n[1/8] Loading raw records...")

    if not settings.paths.raw_records_json.exists():
        raise FileNotFoundError(
            f"Raw records not found: {settings.paths.raw_records_json}"
        )

    raw_records = load_raw_records(settings.paths.raw_records_json)
    print(f"      Loaded {len(raw_records)} raw records.")

    # 2. Clean data
    print("\n[2/8] Cleaning data...")

    clean_df = build_clean_dataframe(
        raw_records,
        datetime.now(UTC),
    )

    print(f"      Clean rows: {len(clean_df)}")

    # 3. Save clean CSV / JSON
    print("\n[3/8] Saving clean data...")

    write_csv(clean_df, settings.paths.clean_csv)

    clean_df.to_json(
        settings.paths.clean_json,
        orient="records",
        force_ascii=False,
        indent=2,
        date_format="iso",
    )

    print(f"      CSV : {settings.paths.clean_csv}")
    print(f"      JSON: {settings.paths.clean_json}")

    # 4. Build Chroma index
    print("\n[4/8] Building Chroma embedding index...")

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )

    print(f"      Collection: {index.collection_name}")
    print(f"      Documents : {len(index.documents)}")
    print(f"      Chroma dir: {index.persist_path}")

    # 5. Evaluation set
    print("\n[5/8] Preparing evaluation set...")

    test_set = _load_or_build_test_set(
        clean_df,
        settings,
    )

    print(f"      Evaluation questions: {len(test_set)}")

    # 6. Evaluate baseline
    print("\n[6/8] Evaluating baseline RAG...")

    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    metrics = bundle.summary

    print(f"      Retrieval Hit Rate: {metrics['retrieval_hit_rate']:.4f}")
    print(f"      Mean Token F1     : {metrics['mean_token_f1']:.4f}")
    print(f"      Judge Accuracy    : {metrics['judge_accuracy']:.4f}")
    print(f"      Mean Judge Score  : {metrics['mean_judge_score']:.4f}/5")

    # 7. Quality + freshness
    print("\n[7/8] Running data-quality and freshness checks...")

    quality = run_data_quality_checks(
        clean_df,
        settings,
        "baseline",
    )

    freshness_report = build_freshness_report(
        clean_df,
        settings,
        settings.paths.freshness_report,
    )

    print(
        f"      Quality Gate: "
        f"{'PASS' if quality['success'] else 'FAIL'}"
    )
    print(
        f"      GX: "
        f"{'PASS' if quality['gx_success'] else 'FAIL'}"
    )
    print(
        f"      Freshness: "
        f"{'PASS' if quality['freshness']['is_fresh'] else 'FAIL'}"
    )
    print(
        f"      Stale rows: "
        f"{quality['freshness']['stale_rows']}/"
        f"{quality['freshness']['total_rows']}"
    )

    # 8. Markdown report
    print("\n[8/8] Writing Phase 1 report...")

    report = _build_report(
        settings=settings,
        row_count=len(clean_df),
        eval_count=len(test_set),
        metrics=metrics,
        quality=quality,
        freshness_report=freshness_report,
    )

    write_text(
        settings.paths.baseline_report,
        report,
    )

    print(f"      Report: {settings.paths.baseline_report}")

    print("\n" + "=" * 70)
    print(
        "PHASE 1 RESULT: "
        + ("PASS" if quality["success"] else "FAIL")
    )
    print("=" * 70)


if __name__ == "__main__":
    main()