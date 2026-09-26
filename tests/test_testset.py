from __future__ import annotations

import json

import pandas as pd
import pytest

from evaluation.testset import build_test_set


def clean_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "paper_id": f"10.1234/{number:02d}",
                "title": f"Paper {number:02d}",
                "summary": f"Finding {number:02d}. More detail.",
                "authors_joined": f"Author {number:02d}, Coauthor {number:02d}",
                "published": f"2026-09-{number:02d}",
                "categories_joined": f"Field {number:02d}, Research",
            }
            for number in range(1, 13)
        ]
    )


def test_build_test_set_writes_ten_questions_with_required_distribution(tmp_path):
    output = tmp_path / "nested" / "test_set.json"

    items = build_test_set(clean_rows(), output)

    assert len(items) == 10
    assert [item["id"] for item in items] == [f"q{number:02d}" for number in range(1, 11)]
    assert [item["question_type"] for item in items] == (
        ["summary"] * 3 + ["authors"] * 3 + ["date"] * 2 + ["categories"] * 2
    )
    assert [item["ground_truth_doc_ids"] for item in items] == [
        [f"10.1234/{number:02d}"] for number in range(12, 2, -1)
    ]
    assert all(f"'Paper {number:02d}'" in item["question"] for number, item in zip(range(12, 2, -1), items))
    assert [item["ground_truth"] for item in items] == [
        "Finding 12.", "Finding 11.", "Finding 10.",
        "Author 09, Coauthor 09", "Author 08, Coauthor 08", "Author 07, Coauthor 07",
        "2026-09-06", "2026-09-05",
        "Field 04, Research", "Field 03, Research",
    ]
    assert set(items[0]) == {
        "id", "question_type", "question", "ground_truth", "ground_truth_doc_ids"
    }
    assert json.loads(output.read_text(encoding="utf-8")) == items


def test_build_test_set_is_deterministic(tmp_path):
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    rows = clean_rows()

    first = build_test_set(rows, first_path)
    second = build_test_set(rows.sample(frac=1, random_state=42), second_path)

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()


def test_build_test_set_rejects_insufficient_rows(tmp_path):
    rows = clean_rows().head(9)
    rows.loc[len(rows)] = {
        "paper_id": "10.1234/invalid",
        "title": "",
        "summary": "Unused summary.",
        "authors_joined": "Unused Author",
        "published": "2026-09-20",
        "categories_joined": "Unused Category",
    }
    output = tmp_path / "test_set.json"

    with pytest.raises(ValueError, match=r"at least 10 valid rows.*found 9"):
        build_test_set(rows, output)

    assert not output.exists()
