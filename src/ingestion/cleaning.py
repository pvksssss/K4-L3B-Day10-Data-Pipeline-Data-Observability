from __future__ import annotations

from datetime import datetime
from html import unescape
import re

import pandas as pd

from ingestion.crossref import PaperRecord


CLEAN_COLUMNS = [
    "paper_id", "title", "summary", "authors", "categories",
    "primary_category", "published", "updated", "abs_url", "pdf_url",
    "comment", "authors_joined", "categories_joined", "summary_chars",
    "age_days", "text_for_embedding",
]


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    without_tags = re.sub(r"<[^>]*>", " ", unescape(str(value)))
    normalized = " ".join(without_tags.split())
    return re.sub(r"\s+([.,;:!?])", r"\1", normalized)


def _clean_list(value: object) -> list[str]:
    items = value if isinstance(value, (list, tuple)) else [value]
    return [text for item in items if (text := _clean_text(item))]


def _iso_date(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.date().isoformat()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize usable paper records into the fixed pre-embedding schema."""
    run_day = pd.Timestamp(run_date).date()
    rows: list[dict] = []
    seen_ids: set[str] = set()

    for record in records:
        paper_id = _clean_text(record.paper_id)
        title = _clean_text(record.title)
        summary = _clean_text(record.summary)
        published = _iso_date(record.published)
        if not paper_id or not title or not summary or not published or paper_id in seen_ids:
            continue

        seen_ids.add(paper_id)
        authors = _clean_list(record.authors)
        categories = _clean_list(record.categories)
        primary_category = _clean_text(record.primary_category) or (categories[0] if categories else "")
        updated = _iso_date(record.updated) or published
        authors_joined = ", ".join(authors)
        categories_joined = ", ".join(categories)
        text_for_embedding = "\n".join(
            (
                f"Title: {title}",
                f"Authors: {authors_joined}",
                f"Published: {published}",
                f"Categories: {categories_joined}",
                f"Summary: {summary}",
            )
        )
        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "primary_category": primary_category,
                "published": published,
                "updated": updated,
                "abs_url": _clean_text(record.abs_url),
                "pdf_url": _clean_text(record.pdf_url),
                "comment": _clean_text(record.comment),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": len(summary),
                "age_days": (run_day - pd.Timestamp(published).date()).days,
                "text_for_embedding": text_for_embedding,
            }
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    return df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
