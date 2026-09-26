from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
import random
from typing import Any

import pandas as pd


RANDOM_SEED = 42
NOISE_TEXT = " ### DATA_CORRUPTION_NOISE_9f3x7q ###"


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-serializable values."""
    if pd.isna(value):
        return None

    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass

    return value


def _record_id(row: pd.Series, index: Any) -> Any:
    """Prefer the paper ID for logging, otherwise use the dataframe index."""
    if "paper_id" in row.index and pd.notna(row["paper_id"]):
        return str(row["paper_id"])

    if "doi" in row.index and pd.notna(row["doi"]):
        return str(row["doi"])

    return index


def _log_change(
    log: list[dict[str, Any]],
    *,
    corruption_type: str,
    index: Any,
    row: pd.Series,
    column: str | None = None,
    before: Any = None,
    after: Any = None,
    details: str = "",
) -> None:
    entry: dict[str, Any] = {
        "corruption_type": corruption_type,
        "row_index": _json_value(index),
        "paper_id": _record_id(row, index),
    }

    if column is not None:
        entry["column"] = column
        entry["before"] = _json_value(before)
        entry["after"] = _json_value(after)

    if details:
        entry["details"] = details

    log.append(entry)


def _rebuild_embedding_text(df: pd.DataFrame) -> None:
    """Rebuild text_for_embedding from the available cleaned fields."""
    if "text_for_embedding" not in df.columns:
        return

    text_columns = [
        column
        for column in (
            "title",
            "summary",
            "authors",
            "categories",
            "primary_category",
            "published",
            "comment",
        )
        if column in df.columns
    ]

    if not text_columns:
        return

    def stringify(value: Any) -> str:
        if value is None or pd.isna(value):
            return ""

        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)

        return str(value).strip()

    df["text_for_embedding"] = df[text_columns].apply(
        lambda row: " ".join(
            value
            for value in (stringify(row[column]) for column in text_columns)
            if value
        ),
        axis=1,
    )


def corrupt_clean_dataframe(
    df: pd.DataFrame,
    output_log_path,
) -> pd.DataFrame:
    """Simulate six types of realistic data corruption.

    Corruptions:
    1. Drop 20% of the latest records.
    2. Blank summaries on selected rows.
    3. Inject deterministic noise into summaries.
    4. Truncate titles to fewer than 8 characters.
    5. Move publication dates 365 days into the past.
    6. Duplicate selected rows.

    The function does not mutate the input DataFrame. A corruption log is
    written to ``output_log_path`` and ``text_for_embedding`` is rebuilt
    after all modifications.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("df must be a pandas DataFrame.")

    if df.empty:
        raise ValueError("Cannot corrupt an empty DataFrame.")

    required_columns = {"title", "summary", "published"}
    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            "DataFrame is missing required columns: "
            + ", ".join(sorted(missing))
        )

    corrupted = df.copy(deep=True)
    log: list[dict[str, Any]] = []
    rng = random.Random(RANDOM_SEED)

    # ------------------------------------------------------------------
    # 1. Drop latest 20% of records
    # ------------------------------------------------------------------
    published_dates = pd.to_datetime(
        corrupted["published"],
        errors="coerce",
        utc=True,
    )

    valid_date_mask = published_dates.notna()

    if valid_date_mask.any():
        dated_indices = (
            corrupted.loc[valid_date_mask]
            .assign(_published_date=published_dates[valid_date_mask])
            .sort_values("_published_date", ascending=False)
            .index
            .tolist()
        )

        drop_count = max(1, int(len(corrupted) * 0.20))
        drop_count = min(drop_count, len(dated_indices))

        dropped_indices = dated_indices[:drop_count]

        for index in dropped_indices:
            row = corrupted.loc[index]
            _log_change(
                log,
                corruption_type="drop_latest_records",
                index=index,
                row=row,
                details="Dropped because it belongs to the latest 20% of records.",
            )

        corrupted = corrupted.drop(index=dropped_indices)

    # Nothing else can be meaningfully corrupted if all records were dropped.
    if corrupted.empty:
        output_path = Path(output_log_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(log, handle, ensure_ascii=False, indent=2)
            handle.write("\n")

        return corrupted

    # ------------------------------------------------------------------
    # 2. Blank summary
    # ------------------------------------------------------------------
    available_indices = list(corrupted.index)

    blank_count = max(1, int(len(corrupted) * 0.20))
    blank_count = min(blank_count, len(available_indices))

    blank_indices = rng.sample(available_indices, blank_count)

    for index in blank_indices:
        before = corrupted.at[index, "summary"]

        corrupted.at[index, "summary"] = ""

        _log_change(
            log,
            corruption_type="blank_summary",
            index=index,
            row=corrupted.loc[index],
            column="summary",
            before=before,
            after="",
        )

    # ------------------------------------------------------------------
    # 3. Inject noise into summary
    # ------------------------------------------------------------------
    available_indices = list(corrupted.index)

    noise_count = max(1, int(len(corrupted) * 0.20))
    noise_count = min(noise_count, len(available_indices))

    noise_indices = rng.sample(available_indices, noise_count)

    for index in noise_indices:
        before = corrupted.at[index, "summary"]
        before_text = "" if pd.isna(before) else str(before)

        after = f"{before_text}{NOISE_TEXT}"
        corrupted.at[index, "summary"] = after

        _log_change(
            log,
            corruption_type="inject_noise",
            index=index,
            row=corrupted.loc[index],
            column="summary",
            before=before,
            after=after,
            details="Injected deterministic synthetic noise.",
        )

    # ------------------------------------------------------------------
    # 4. Truncate titles to fewer than 8 characters
    # ------------------------------------------------------------------
    available_indices = [
        index
        for index in corrupted.index
        if not pd.isna(corrupted.at[index, "title"])
        and len(str(corrupted.at[index, "title"]).strip()) >= 8
    ]

    if available_indices:
        truncate_count = max(1, int(len(corrupted) * 0.20))
        truncate_count = min(truncate_count, len(available_indices))

        truncate_indices = rng.sample(available_indices, truncate_count)

        for index in truncate_indices:
            before = corrupted.at[index, "title"]
            title = str(before).strip()

            # Seven characters guarantees the corrupted title is < 8 chars.
            after = title[:7]

            corrupted.at[index, "title"] = after

            _log_change(
                log,
                corruption_type="truncate_title",
                index=index,
                row=corrupted.loc[index],
                column="title",
                before=before,
                after=after,
                details="Title truncated to at most 7 characters.",
            )

    # ------------------------------------------------------------------
    # 5. Make publication date stale by 365 days
    # ------------------------------------------------------------------
    published_dates = pd.to_datetime(
        corrupted["published"],
        errors="coerce",
        utc=True,
    )

    available_indices = [
        index
        for index in corrupted.index
        if pd.notna(published_dates.loc[index])
    ]

    if available_indices:
        stale_count = max(1, int(len(corrupted) * 0.20))
        stale_count = min(stale_count, len(available_indices))

        stale_indices = rng.sample(available_indices, stale_count)

        for index in stale_indices:
            before = corrupted.at[index, "published"]
            date = published_dates.loc[index]

            stale_date = date - timedelta(days=365)

            # Preserve the simple YYYY-MM-DD representation used by the
            # ingestion layer whenever possible.
            after = stale_date.strftime("%Y-%m-%d")

            corrupted.at[index, "published"] = after

            _log_change(
                log,
                corruption_type="stale_date",
                index=index,
                row=corrupted.loc[index],
                column="published",
                before=before,
                after=after,
                details="Publication date moved 365 days into the past.",
            )

    # ------------------------------------------------------------------
    # 6. Duplicate rows
    # ------------------------------------------------------------------
    available_indices = list(corrupted.index)

    duplicate_count = max(1, int(len(corrupted) * 0.20))
    duplicate_count = min(duplicate_count, len(available_indices))

    duplicate_indices = rng.sample(available_indices, duplicate_count)

    duplicates = corrupted.loc[duplicate_indices].copy()

    # Give duplicated rows fresh dataframe indices so they are actual
    # duplicate records rather than index collisions.
    duplicates.index = range(
        len(corrupted),
        len(corrupted) + len(duplicates),
    )

    for source_index, (_, duplicate_row) in zip(
        duplicate_indices,
        duplicates.iterrows(),
    ):
        _log_change(
            log,
            corruption_type="duplicate_row",
            index=duplicate_row.name,
            row=duplicate_row,
            details=f"Duplicated source row {source_index}.",
        )

    corrupted = pd.concat([corrupted, duplicates], axis=0)

    # ------------------------------------------------------------------
    # 7. Rebuild embedding text after all mutations
    # ------------------------------------------------------------------
    _rebuild_embedding_text(corrupted)

    # ------------------------------------------------------------------
    # 8. Write corruption log
    # ------------------------------------------------------------------
    output_path = Path(output_log_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(
            log,
            handle,
            ensure_ascii=False,
            indent=2,
        )
        handle.write("\n")

    return corrupted