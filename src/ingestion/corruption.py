from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import write_json


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path | str | None = None) -> pd.DataFrame:
    """Apply 6 synthetic corruption scenarios deterministically to clean dataframe.

    Scenarios:
    1. Drop latest records: drop top 20% (5 records from 24) to simulate missing recent data.
    2. Blank summary: set empty string for summary on rows to trigger GX length failure.
    3. Inject noise: corrupt summary with garbage/gibberish to degrade semantic retrieval.
    4. Truncate title: shorten title to < 8 chars to break exact/title matching.
    5. Stale date: shift published date backwards by 400 days to breach Freshness SLA.
    6. Duplicate rows: duplicate records to violate uniqueness constraints.
    """
    corrupted = df.copy()
    total_records = len(corrupted)
    log_entries: list[dict[str, Any]] = []

    if total_records == 0:
        if output_log_path:
            write_json(Path(output_log_path), log_entries)
        return corrupted

    # 1. Drop latest records (first 20% / 5 rows)
    drop_count = max(1, int(total_records * 0.20))
    dropped_ids = corrupted.iloc[:drop_count]["paper_id"].tolist()
    corrupted = corrupted.iloc[drop_count:].reset_index(drop=True)
    log_entries.append({
        "scenario": "drop_latest_records",
        "description": f"Dropped {drop_count} latest records to simulate ingestion loss.",
        "affected_count": drop_count,
        "affected_ids": dropped_ids,
    })

    # 2. Blank summary on row index 0
    if len(corrupted) > 0:
        row_id = corrupted.iloc[0]["paper_id"]
        corrupted.at[0, "summary"] = ""
        corrupted.at[0, "summary_chars"] = 0
        log_entries.append({
            "scenario": "blank_summary",
            "description": "Cleared summary on record to trigger length validation failure.",
            "affected_count": 1,
            "affected_ids": [row_id],
        })

    # 3. Inject noise into summary on row index 1
    if len(corrupted) > 1:
        row_id = corrupted.iloc[1]["paper_id"]
        corrupted.at[1, "summary"] = "### NOISE CORRUPTED DATA ### [GARBAGE_BYTES_0xDEADBEEF] " * 5
        corrupted.at[1, "summary_chars"] = len(corrupted.at[1, "summary"])
        log_entries.append({
            "scenario": "inject_noise",
            "description": "Injected garbage noise into summary to destroy semantic relevance.",
            "affected_count": 1,
            "affected_ids": [row_id],
        })

    # 4. Truncate title on row index 2 (< 8 characters)
    if len(corrupted) > 2:
        row_id = corrupted.iloc[2]["paper_id"]
        corrupted.at[2, "title"] = "AI RAG"
        log_entries.append({
            "scenario": "truncate_title",
            "description": "Truncated title to < 8 chars to impair lookup and retrieval.",
            "affected_count": 1,
            "affected_ids": [row_id],
        })

    # 5. Stale date on row index 3 and 4 (shift published date back 400 days)
    stale_count = min(6, len(corrupted))
    stale_ids = []
    for idx in range(stale_count):
        row_id = corrupted.iloc[idx]["paper_id"]
        stale_ids.append(row_id)
        current_pub = pd.to_datetime(corrupted.at[idx, "published"])
        stale_pub = (current_pub - pd.Timedelta(days=400)).date().isoformat()
        corrupted.at[idx, "published"] = stale_pub
        corrupted.at[idx, "age_days"] = int(corrupted.at[idx, "age_days"]) + 400
    log_entries.append({
        "scenario": "stale_date",
        "description": f"Shifted published date back by 400 days on {stale_count} records to violate Freshness SLA (>25% stale).",
        "affected_count": stale_count,
        "affected_ids": stale_ids,
    })

    # 6. Duplicate row: duplicate index 0
    if len(corrupted) > 0:
        dup_row = corrupted.iloc[[0]]
        corrupted = pd.concat([corrupted, dup_row], ignore_index=True)
        log_entries.append({
            "scenario": "duplicate_rows",
            "description": "Duplicated record to trigger uniqueness validation violation.",
            "affected_count": 1,
            "affected_ids": [dup_row.iloc[0]["paper_id"]],
        })

    # Rebuild text_for_embedding on all rows
    rebuilt_texts = []
    for _, row in corrupted.iterrows():
        rebuilt_texts.append(
            "\n".join(
                (
                    f"Title: {row['title']}",
                    f"Authors: {row['authors_joined']}",
                    f"Published: {row['published']}",
                    f"Categories: {row['categories_joined']}",
                    f"Summary: {row['summary']}",
                )
            )
        )
    corrupted["text_for_embedding"] = rebuilt_texts

    if output_log_path:
        write_json(Path(output_log_path), log_entries)

    return corrupted
