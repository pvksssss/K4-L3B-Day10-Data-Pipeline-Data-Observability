from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import json

import pandas as pd

from core.config import load_settings
from core.utils import write_json
from evaluation.metrics import EvaluationBundle
from ingestion.crossref import PaperRecord
from pipelines import phase1
from retrieval.index import SearchResult
from retrieval.qa import answer_question


def test_phase1_main_runs_stages_in_order_and_persists_contracts(tmp_path, monkeypatch):
    settings = replace(load_settings(tmp_path), llm_provider="mock", refresh_source=False, refresh_test_set=False)
    published = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    records = [
        PaperRecord(
            paper_id=f"10.1234/{number:02d}", title=f"Paper {number:02d}",
            summary=f"Finding for paper {number:02d} is described in sufficient detail.",
            authors=[f"Author {number:02d}"], categories=["Research"], primary_category="Research",
            published=published, updated=published, abs_url=f"https://doi.org/10.1234/{number:02d}",
            pdf_url=f"https://doi.org/10.1234/{number:02d}", comment="Crossref snapshot",
        )
        for number in range(10)
    ]
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    monkeypatch.setattr(phase1, "load_settings", lambda: settings, raising=False)

    class LightweightIndex:
        @classmethod
        def build(cls, df, used_settings, embeddings_output_path=None):
            assert used_settings is settings
            assert len(pd.read_csv(settings.paths.clean_csv)) == 10
            assert len(json.loads(settings.paths.clean_json.read_text(encoding="utf-8"))) == 10
            assert set(df["paper_id"]) == {record.paper_id for record in records}
            assert embeddings_output_path == settings.paths.embeddings_json
            write_json(embeddings_output_path, {
                "backend": "chroma", "collection_name": "papers-baseline",
                "documents": [{"paper_id": row.paper_id} for row in df.itertuples()],
            })
            return cls()

    def lightweight_evaluate(used_settings, index, test_set_path, metrics_output_path, answers_output_path):
        assert used_settings is settings and isinstance(index, LightweightIndex)
        assert settings.paths.embeddings_json.exists()
        assert test_set_path == settings.paths.eval_testset
        questions = json.loads(test_set_path.read_text(encoding="utf-8"))
        assert len(questions) == 10
        assert {item["ground_truth_doc_ids"][0] for item in questions} == {record.paper_id for record in records}
        summary = {
            "samples": 10, "retrieval_hit_rate": 1.0, "mean_token_f1": 0.8,
            "judge_accuracy": 0.9, "mean_judge_score": 4.0,
        }
        answers = [{"id": item["id"], "answer": item["ground_truth"]} for item in questions]
        write_json(metrics_output_path, summary)
        write_json(answers_output_path, answers)
        return EvaluationBundle(summary=summary, answers=answers)

    monkeypatch.setattr(phase1, "LocalEmbeddingIndex", LightweightIndex, raising=False)
    monkeypatch.setattr(phase1, "evaluate_pipeline", lightweight_evaluate, raising=False)

    phase1.main()

    assert len(json.loads(settings.paths.clean_json.read_text(encoding="utf-8"))) == 10
    assert len(json.loads(settings.paths.embeddings_json.read_text(encoding="utf-8"))["documents"]) == 10
    assert len(json.loads(settings.paths.eval_testset.read_text(encoding="utf-8"))) == 10
    assert json.loads(settings.paths.baseline_metrics.read_text(encoding="utf-8"))["samples"] == 10
    assert len(json.loads(settings.paths.baseline_answers.read_text(encoding="utf-8"))) == 10
    quality = json.loads(settings.paths.baseline_quality_report.read_text(encoding="utf-8"))
    freshness = json.loads(settings.paths.freshness_report.read_text(encoding="utf-8"))
    assert quality["success"] is True and freshness["is_fresh"] is True
    report = settings.paths.baseline_report.read_text(encoding="utf-8")
    assert "10" in report and "1.000" in report and "0.800" in report
    assert "papers_clean.csv" in report and "baseline_metrics.json" in report


def test_exact_title_lookup_accepts_apostrophe_inside_title(tmp_path):
    title = "A Scholar's Guide to Retrieval"
    matching = {
        "paper_id": "10.1234/match", "title": title, "content": "Matching paper content",
        "metadata": {"summary": "The matching finding is here.", "authors_joined": "Author Match",
                     "published": "2026-09-20", "categories_joined": "Research"},
    }
    decoy = SearchResult(
        paper_id="10.1234/decoy", title="Unrelated paper", score=0.9,
        content="Unrelated paper content", metadata={
            "summary": "An unrelated finding.", "authors_joined": "Other Author",
            "published": "2026-09-20", "categories_joined": "Other",
        },
    )

    class Index:
        def lookup(self, value):
            return matching if value == title else None

        def search(self, query, top_k=None):
            return [decoy]

    result = answer_question(f"What is the summary of '{title}'?", load_settings(tmp_path), Index())

    assert result.answer == "The matching finding is here."
    assert result.retrieved_doc_ids[0] == "10.1234/match"
