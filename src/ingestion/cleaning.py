from __future__ import annotations

from datetime import datetime

import pandas as pd

from ingestion.crossref import PaperRecord


def _clean_text(value: object) -> str:
    """Normalize a scalar text value."""
    if value is None:
        return ""

    text = str(value).strip()
    return " ".join(text.split())


def _clean_list(values: list[str] | None) -> list[str]:
    """Normalize and deduplicate a list of strings while preserving order."""
    if not values:
        return []

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = _clean_text(value)

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key not in seen:
            seen.add(key)
            result.append(cleaned)

    return result


def _parse_date(value: str) -> pd.Timestamp | pd.NaT:
    """Parse a date into a timezone-naive pandas Timestamp."""
    if not value:
        return pd.NaT

    parsed = pd.to_datetime(value, errors="coerce", utc=True)

    if pd.isna(parsed):
        return pd.NaT

    return parsed.tz_convert(None)


def _calculate_age_days(
    published: pd.Timestamp | pd.NaT,
    run_date: datetime,
) -> float | None:
    """Calculate document age in days relative to the pipeline run date."""
    if pd.isna(published):
        return None

    run_timestamp = pd.Timestamp(run_date)

    if run_timestamp.tzinfo is not None:
        run_timestamp = run_timestamp.tz_convert(None)

    age = (run_timestamp - published).total_seconds() / 86400

    # Future publication dates are considered age 0 rather than negative.
    return max(0.0, age)


def build_clean_dataframe(
    records: list[PaperRecord],
    run_date: datetime,
) -> pd.DataFrame:
    """Clean raw Crossref records into an embedding-ready DataFrame.

    The resulting DataFrame contains normalized paper metadata plus:
      - authors_joined
      - categories_joined
      - summary_chars
      - age_days
      - text_for_embedding
    """
    if not isinstance(records, list):
        raise TypeError("records must be a list of PaperRecord objects.")

    if not isinstance(run_date, datetime):
        raise TypeError("run_date must be a datetime.")

    rows: list[dict[str, object]] = []

    for record in records:
        if not isinstance(record, PaperRecord):
            continue

        paper_id = _clean_text(record.paper_id)
        title = _clean_text(record.title)
        summary = _clean_text(record.summary)

        authors = _clean_list(record.authors)
        categories = _clean_list(record.categories)

        primary_category = _clean_text(record.primary_category)

        # If primary_category is absent, use the first normalized category.
        if not primary_category and categories:
            primary_category = categories[0]

        published = _parse_date(
            _clean_text(record.published)
        )

        updated = _parse_date(
            _clean_text(record.updated)
        )

        authors_joined = ", ".join(authors)
        categories_joined = ", ".join(categories)

        summary_chars = len(summary)

        age_days = _calculate_age_days(
            published,
            run_date,
        )

        # Build one consistent text representation for embeddings.
        text_parts = [
            title,
            summary,
            authors_joined,
            categories_joined,
            primary_category,
            _clean_text(record.comment),
        ]

        text_for_embedding = "\n".join(
            part
            for part in text_parts
            if part
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
                "summary_chars": summary_chars,
                "age_days": age_days,
                "text_for_embedding": text_for_embedding,
            }
        )

    columns = [
        "paper_id",
        "title",
        "summary",
        "authors",
        "categories",
        "primary_category",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "comment",
        "authors_joined",
        "categories_joined",
        "summary_chars",
        "age_days",
        "text_for_embedding",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows, columns=columns)

    # ---------------------------------------------------------------
    # Normalize column types
    # ---------------------------------------------------------------
    for column in (
        "paper_id",
        "title",
        "summary",
        "primary_category",
        "abs_url",
        "pdf_url",
        "comment",
        "authors_joined",
        "categories_joined",
        "text_for_embedding",
    ):
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["summary_chars"] = (
        df["summary"]
        .str.len()
        .astype(int)
    )

    df["age_days"] = pd.to_numeric(
        df["age_days"],
        errors="coerce",
    )

    # ---------------------------------------------------------------
    # Drop structurally invalid records
    # ---------------------------------------------------------------
    valid_mask = (
        df["paper_id"].ne("")
        & df["title"].ne("")
        & df["summary"].ne("")
    )

    df = df.loc[valid_mask].copy()

    # ---------------------------------------------------------------
    # Remove duplicate documents
    # ---------------------------------------------------------------
    df = (
        df.drop_duplicates(
            subset=["paper_id"],
            keep="first",
        )
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------------
    # Stable deterministic ordering
    # ---------------------------------------------------------------
    df = (
        df.sort_values(
            by=["published", "paper_id"],
            ascending=[False, True],
            na_position="last",
        )
        .reset_index(drop=True)
    )

    return df
