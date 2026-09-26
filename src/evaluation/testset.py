from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


def _clean_text(value: Any) -> str:
    """Normalize a dataframe cell into plain text."""
    if value is None or pd.isna(value):
        return ""

    if isinstance(value, (list, tuple)):
        return ", ".join(
            str(item).strip()
            for item in value
            if item is not None and str(item).strip()
        )

    return re.sub(r"\s+", " ", str(value)).strip()


def _first_sentence(text: str) -> str:
    """Return the first sentence from a summary."""
    text = _clean_text(text)

    if not text:
        return ""

    # Prefer sentence boundaries followed by whitespace/capitalization.
    match = re.search(r"^(.+?[.!?])(?:\s|$)", text)
    if match:
        return match.group(1).strip()

    # If the abstract has no obvious sentence boundary, use the whole text.
    return text


def _authors_text(value: Any) -> str:
    """Normalize author data into a readable answer."""
    if isinstance(value, (list, tuple)):
        authors = [
            _clean_text(author)
            for author in value
            if _clean_text(author)
        ]
        return ", ".join(authors)

    return _clean_text(value)


def _categories_text(value: Any) -> str:
    """Normalize category data into a readable answer."""
    if isinstance(value, (list, tuple)):
        categories = [
            _clean_text(category)
            for category in value
            if _clean_text(category)
        ]
        return ", ".join(categories)

    return _clean_text(value)


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tạo bộ evaluation set từ cleaned dataframe.

    Tạo 10 câu hỏi, phân bổ:
      - 3 summary
      - 3 authors
      - 2 date
      - 2 categories

    Mỗi câu hỏi chứa:
      - id
      - question_type
      - question
      - ground_truth
      - ground_truth_doc_ids

    Kết quả được ghi dưới dạng JSON UTF-8 vào ``output_path``.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    if df.empty:
        raise ValueError("Cannot build evaluation test set from an empty DataFrame.")

    required_columns = {
        "paper_id",
        "title",
        "summary",
        "authors",
        "published",
        "categories",
    }

    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            "DataFrame is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    # Keep only rows that have the minimum information required to identify
    # and ask questions about a paper.
    papers = df.copy()

    papers["_paper_id"] = papers["paper_id"].map(_clean_text)
    papers["_title"] = papers["title"].map(_clean_text)
    papers["_summary"] = papers["summary"].map(_clean_text)
    papers["_authors"] = papers["authors"].map(_authors_text)
    papers["_published"] = papers["published"].map(_clean_text)
    papers["_categories"] = papers["categories"].map(_categories_text)

    papers = papers[
        (papers["_paper_id"] != "")
        & (papers["_title"] != "")
    ].drop_duplicates(subset=["_paper_id"])

    if len(papers) < 10:
        raise ValueError(
            f"At least 10 valid documents are required to build the test set; "
            f"found {len(papers)}."
        )

    # Deterministic selection makes the benchmark reproducible.
    papers = papers.sort_values("_paper_id").reset_index(drop=True)

    # Prefer papers that actually contain the information required by each
    # question type. This avoids empty ground-truth answers.
    summary_papers = papers[papers["_summary"] != ""]
    author_papers = papers[papers["_authors"] != ""]
    date_papers = papers[papers["_published"] != ""]
    category_papers = papers[papers["_categories"] != ""]

    if len(summary_papers) < 3:
        raise ValueError("At least 3 papers with non-empty summaries are required.")

    if len(author_papers) < 3:
        raise ValueError("At least 3 papers with non-empty authors are required.")

    if len(date_papers) < 2:
        raise ValueError("At least 2 papers with non-empty publication dates are required.")

    if len(category_papers) < 2:
        raise ValueError("At least 2 papers with non-empty categories are required.")

    # Select distinct documents whenever possible. This gives the benchmark
    # broader document coverage instead of asking several questions about
    # the same paper.
    selected: list[tuple[str, pd.Series]] = []
    used_ids: set[str] = set()

    def select_rows(source: pd.DataFrame, count: int) -> list[pd.Series]:
        result: list[pd.Series] = []

        for _, row in source.iterrows():
            paper_id = row["_paper_id"]

            if paper_id in used_ids:
                continue

            result.append(row)
            used_ids.add(paper_id)

            if len(result) == count:
                break

        # If the current category cannot provide enough unused documents,
        # allow reuse as a last resort.
        if len(result) < count:
            for _, row in source.iterrows():
                if len(result) == count:
                    break

                if row["_paper_id"] not in {r["_paper_id"] for r in result}:
                    result.append(row)

        return result

    selected_summary = select_rows(summary_papers, 3)
    selected_authors = select_rows(author_papers, 3)
    selected_date = select_rows(date_papers, 2)
    selected_categories = select_rows(category_papers, 2)

    if (
        len(selected_summary) < 3
        or len(selected_authors) < 3
        or len(selected_date) < 2
        or len(selected_categories) < 2
    ):
        raise ValueError("Unable to construct the required 10 evaluation questions.")

    questions: list[dict[str, Any]] = []

    def add_question(
        question_type: str,
        row: pd.Series,
        question: str,
        ground_truth: str,
    ) -> None:
        paper_id = row["_paper_id"]

        questions.append(
            {
                "id": f"eval_{len(questions) + 1:03d}",
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [paper_id],
            }
        )

    for row in selected_summary:
        title = row["_title"]
        ground_truth = _first_sentence(row["_summary"])

        add_question(
            "summary",
            row,
            f"What is the summary of the paper '{title}'?",
            ground_truth,
        )

    for row in selected_authors:
        title = row["_title"]

        add_question(
            "authors",
            row,
            f"Who are the authors of the paper '{title}'?",
            row["_authors"],
        )

    for row in selected_date:
        title = row["_title"]

        add_question(
            "date",
            row,
            f"When was the paper '{title}' published?",
            row["_published"],
        )

    for row in selected_categories:
        title = row["_title"]

        add_question(
            "categories",
            row,
            f"What are the research categories of the paper '{title}'?",
            row["_categories"],
        )

    if len(questions) != 10:
        raise RuntimeError(
            f"Expected 10 evaluation questions, generated {len(questions)}."
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(
            questions,
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")

    return questions