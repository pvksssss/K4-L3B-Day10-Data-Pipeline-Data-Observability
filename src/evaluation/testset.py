from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json


QUESTION_TYPES = ("summary",) * 3 + ("authors",) * 3 + ("date",) * 2 + ("categories",) * 2
REQUIRED_COLUMNS = ("paper_id", "title", "summary", "authors_joined", "published", "categories_joined")


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build and persist ten reproducible questions from normalized papers."""
    valid = df.dropna(subset=list(REQUIRED_COLUMNS))
    for column in REQUIRED_COLUMNS:
        valid = valid[valid[column].astype(str).str.strip().ne("")]
    valid = valid.sort_values(["published", "paper_id"], ascending=[False, True])
    if len(valid) < 10:
        raise ValueError(f"Evaluation test set requires at least 10 valid rows; found {len(valid)}")

    items: list[dict[str, Any]] = []
    for number, (question_type, row) in enumerate(zip(QUESTION_TYPES, valid.head(10).to_dict("records")), 1):
        title = row["title"]
        if question_type == "summary":
            question = f"What is the summary of '{title}'?"
            ground_truth = first_sentence(row["summary"])
        elif question_type == "authors":
            question = f"Who authored '{title}'?"
            ground_truth = row["authors_joined"]
        elif question_type == "date":
            question = f"When was '{title}' published?"
            ground_truth = row["published"]
        else:
            question = f"What categories is '{title}' in?"
            ground_truth = row["categories_joined"]
        items.append(
            {
                "id": f"q{number:02d}",
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [row["paper_id"]],
            }
        )

    write_json(Path(output_path), items)
    return items
