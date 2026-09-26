from __future__ import annotations

import pandas as pd
import pytest

from core.utils import read_json
from ingestion.corruption import corrupt_clean_dataframe


def _sample_df(count: int = 24) -> pd.DataFrame:
    rows = []
    for i in range(count):
        rows.append(
            {
                "paper_id": f"10.1000/{i:03d}",
                "title": f"Scientific Paper Number {i} On Artificial Intelligence",
                "summary": f"This is an extensive abstract for paper number {i} detailing novel deep learning architectures.",
                "authors": ["Alice Smith", "Bob Jones"],
                "authors_joined": "Alice Smith, Bob Jones",
                "categories": ["Computer Science", "AI"],
                "categories_joined": "Computer Science, AI",
                "primary_category": "Computer Science",
                "published": f"2026-06-{(i % 28) + 1:02d}",
                "updated": f"2026-06-{(i % 28) + 1:02d}",
                "abs_url": f"https://doi.org/10.1000/{i:03d}",
                "pdf_url": f"https://doi.org/10.1000/{i:03d}.pdf",
                "comment": f"Sample paper {i}",
                "summary_chars": 80,
                "age_days": 10 + i,
                "text_for_embedding": f"Title: Paper {i}\nSummary: Summary {i}",
            }
        )
    return pd.DataFrame(rows)


def test_corrupt_clean_dataframe_applies_all_six_scenarios(tmp_path):
    log_path = tmp_path / "corruption_log.json"
    df = _sample_df(24)
    corrupted = corrupt_clean_dataframe(df, output_log_path=log_path)

    # 1. Dropped 20% (4-5 rows) + 1 duplicate added
    assert len(corrupted) < len(df) + 1
    # 2. Blank summary on index 0
    assert corrupted.iloc[0]["summary"] == ""
    # 3. Injected noise on index 1
    assert "### NOISE CORRUPTED DATA ###" in corrupted.iloc[1]["summary"]
    # 4. Truncated title on index 2
    assert len(corrupted.iloc[2]["title"]) < 8
    # 5. Duplicate row exists
    assert corrupted["paper_id"].duplicated().any()
    # 6. Log contains all 6 scenarios
    assert log_path.exists()
    log_data = read_json(log_path)
    assert len(log_data) == 6
    scenarios = {item["scenario"] for item in log_data}
    assert scenarios == {
        "drop_latest_records",
        "blank_summary",
        "inject_noise",
        "truncate_title",
        "stale_date",
        "duplicate_rows",
    }


def test_corrupt_clean_dataframe_empty_input(tmp_path):
    log_path = tmp_path / "empty_log.json"
    empty_df = pd.DataFrame()
    corrupted = corrupt_clean_dataframe(empty_df, output_log_path=log_path)
    assert corrupted.empty
    assert log_path.exists()
    assert read_json(log_path) == []
