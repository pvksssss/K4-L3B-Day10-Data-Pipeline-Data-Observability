from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import PaperRecord


COLUMNS = [
    "paper_id", "title", "summary", "authors", "categories",
    "primary_category", "published", "updated", "abs_url", "pdf_url",
    "comment", "authors_joined", "categories_joined", "summary_chars",
    "age_days", "text_for_embedding",
]


def paper(**changes) -> PaperRecord:
    record = PaperRecord(
        paper_id="10.1234/one",
        title="First paper",
        summary="Useful result.",
        authors=["Ada Lovelace"],
        categories=["Data Science"],
        primary_category="Data Science",
        published="2026-09-20",
        updated="2026-09-21",
        abs_url="https://doi.org/10.1234/one",
        pdf_url="https://example.org/one.pdf",
        comment="Peer reviewed",
    )
    return replace(record, **changes)


def test_build_clean_dataframe_normalizes_schema_and_embedding_text():
    record = paper(
        paper_id=" 10.1234/one ",
        title="<b> First&nbsp; paper </b>\n",
        summary="<jats:p>Useful <i>result</i>.\n Second line.</jats:p>",
        authors=[" Ada  Lovelace ", "<em>Grace</em> Hopper"],
        categories=[" Data   Science ", "<i>AI</i>"],
        primary_category=" <b>Data Science</b> ",
        published="2026-09-20T23:40:00+07:00",
        updated="2026-09-21 08:00:00",
        abs_url=" https://doi.org/10.1234/one ",
        pdf_url="https://example.org/one.pdf\n",
        comment=" <p>Peer  reviewed</p> ",
    )

    df = build_clean_dataframe([record], datetime(2026, 9, 26, tzinfo=timezone(timedelta(hours=7))))

    assert list(df.columns) == COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    assert row["paper_id"] == "10.1234/one"
    assert row["title"] == "First paper"
    assert row["summary"] == "Useful result. Second line."
    assert row["authors"] == ["Ada Lovelace", "Grace Hopper"]
    assert row["categories"] == ["Data Science", "AI"]
    assert row["primary_category"] == "Data Science"
    assert row["published"] == "2026-09-20"
    assert row["updated"] == "2026-09-21"
    assert row["abs_url"] == "https://doi.org/10.1234/one"
    assert row["pdf_url"] == "https://example.org/one.pdf"
    assert row["comment"] == "Peer reviewed"
    assert row["authors_joined"] == "Ada Lovelace, Grace Hopper"
    assert row["categories_joined"] == "Data Science, AI"
    assert row["summary_chars"] == len("Useful result. Second line.")
    assert row["age_days"] == 6
    assert row["text_for_embedding"] == (
        "Title: First paper\n"
        "Authors: Ada Lovelace, Grace Hopper\n"
        "Published: 2026-09-20\n"
        "Categories: Data Science, AI\n"
        "Summary: Useful result. Second line."
    )


def test_build_clean_dataframe_deduplicates_and_filters_invalid_rows():
    records = [
        paper(paper_id="10.1234/z", published="2026-09-20"),
        paper(paper_id="10.1234/a", published="2026-09-22", title="First accepted"),
        paper(paper_id=" 10.1234/a ", published="2026-09-25", title="Later duplicate"),
        paper(paper_id="10.1234/b", published="2026-09-22", title="Same day"),
        paper(paper_id="10.1234/invalid", published="not a date"),
        paper(paper_id=" <b> </b> "),
        paper(paper_id="10.1234/no-title", title="<i> </i>"),
        paper(paper_id="10.1234/no-summary", summary="<p> </p>"),
    ]

    df = build_clean_dataframe(records, datetime(2026, 9, 26))

    assert df["paper_id"].tolist() == ["10.1234/a", "10.1234/b", "10.1234/z"]
    assert df["title"].tolist() == ["First accepted", "Same day", "First paper"]
    assert df["published"].tolist() == ["2026-09-22", "2026-09-22", "2026-09-20"]
    assert df["age_days"].tolist() == [4, 4, 6]


def test_build_clean_dataframe_normalizes_mixed_collection_values():
    records = [
        paper(
            paper_id="10.1234/tuple",
            authors=("<b>Ada</b>", None, "  ", "Grace  Hopper"),
            categories=" Computer   Science ",
            primary_category="",
            updated="invalid",
        ),
        paper(
            paper_id="10.1234/scalar",
            authors="  Research  Group ",
            categories=("<i>AI</i>", None, "  Data   Science "),
            primary_category="  AI ",
        ),
    ]

    df = build_clean_dataframe(records, datetime(2026, 9, 26))

    by_id = df.set_index("paper_id")
    assert by_id.loc["10.1234/tuple", "authors"] == ["Ada", "Grace Hopper"]
    assert by_id.loc["10.1234/tuple", "categories"] == ["Computer Science"]
    assert by_id.loc["10.1234/tuple", "primary_category"] == "Computer Science"
    assert by_id.loc["10.1234/tuple", "updated"] == "2026-09-20"
    assert by_id.loc["10.1234/scalar", "authors"] == ["Research Group"]
    assert by_id.loc["10.1234/scalar", "categories"] == ["AI", "Data Science"]
    assert by_id.loc["10.1234/scalar", "categories_joined"] == "AI, Data Science"


def test_build_clean_dataframe_empty_input_retains_schema():
    df = build_clean_dataframe([], datetime(2026, 9, 26))

    assert df.empty
    assert list(df.columns) == COLUMNS
