from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import re
import time

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Normalize usable Crossref work items into local paper records."""
    message = payload.get("message") if isinstance(payload, dict) else None
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        return []

    records = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doi = _text(item.get("DOI"))
        title = _text(item.get("title"))
        if not doi or not title:
            continue
        published = _date_text(item.get("published")) or _date_text(item.get("issued")) or _date_text(item.get("created"))
        if not published:
            continue
        updated = _date_text(item.get("updated")) or _date_text(item.get("created")) or published
        categories = _text_list(item.get("subject"))
        url = _text(item.get("URL")) or f"https://doi.org/{doi}"
        pdf_url = next(
            (
                _text(link.get("URL"))
                for link in _as_list(item.get("link"))
                if isinstance(link, dict)
                and _text(link.get("content-type")).lower() == "application/pdf"
                and _text(link.get("URL"))
            ),
            url,
        )
        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=_strip_tags(item.get("abstract")),
                authors=_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=updated,
                abs_url=url,
                pdf_url=pdf_url,
                comment=f"Crossref record {doi}",
            )
        )
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref works, using local snapshots when offline or unrefreshed."""
    paths = settings.paths
    if not settings.refresh_source:
        cached = _load_records_if_present(paths.raw_records_json)
        if cached:
            return cached
        raw = _load_raw_response_if_present(paths.raw_api_response)
        if raw:
            _save_records(paths.raw_records_json, raw)
            return raw

    try:
        with requests.Session() as session:
            for attempt in range(3):
                try:
                    response = session.get(
                        "https://api.crossref.org/works",
                        params={
                            "query": settings.source_query,
                            "filter": settings.source_filter,
                            "rows": settings.max_results,
                        },
                        headers={"User-Agent": "day10-data-observability-lab/0.1 (Crossref research ingestion)"},
                        timeout=10,
                    )
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        time.sleep(_retry_delay(response.headers.get("Retry-After"), attempt))
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    records = parse_crossref_payload(payload)
                    write_json(paths.raw_api_response, payload)
                    _save_records(paths.raw_records_json, records)
                    return records
                except requests.HTTPError:
                    raise
                except requests.RequestException:
                    if attempt == 2:
                        raise
                    time.sleep(0.25 * (attempt + 1))
    except (requests.RequestException, ValueError) as exc:
        raw = _load_raw_response_if_present(paths.raw_api_response)
        if raw:
            _save_records(paths.raw_records_json, raw)
            return raw
        cached = _load_records_if_present(paths.raw_records_json)
        if cached:
            return cached
        raise RuntimeError("Crossref request failed and no usable local snapshot is available") from exc

    raise RuntimeError("Crossref request ended without a response")


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Read a stored normalized-record snapshot."""
    rows = read_json(path)
    if not isinstance(rows, list):
        return []
    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            records.append(PaperRecord(**row))
        except TypeError:
            continue
    return records


def _as_list(value: object) -> list:
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


def _text(value: object) -> str:
    if isinstance(value, list):
        return next((_text(part) for part in value if _text(part)), "")
    return normalize_whitespace(value) if isinstance(value, str) else ""


def _text_list(value: object) -> list[str]:
    return [part for item in _as_list(value) if (part := _text(item))]


def _strip_tags(value: object) -> str:
    return normalize_whitespace(unescape(re.sub(r"<[^>]*>", " ", _text(value))))


def _date_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts")
    if isinstance(parts, list) and parts and isinstance(parts[0], list):
        try:
            year, *rest = parts[0]
            month = rest[0] if rest else 1
            day = rest[1] if len(rest) > 1 else 1
            return date(int(year), int(month), int(day)).isoformat()
        except (TypeError, ValueError):
            return ""
    stamp = _text(value.get("date-time"))
    if stamp:
        try:
            return date.fromisoformat(stamp[:10]).isoformat()
        except ValueError:
            return ""
    return ""


def _authors(value: object) -> list[str]:
    names = []
    for author in _as_list(value):
        if not isinstance(author, dict):
            continue
        name = _text(author.get("name")) or normalize_whitespace(
            f"{_text(author.get('given'))} {_text(author.get('family'))}"
        )
        if name:
            names.append(name)
    return names


def _save_records(path: Path, records: list[PaperRecord]) -> None:
    write_json(path, [asdict(record) for record in records])


def _load_records_if_present(path: Path) -> list[PaperRecord]:
    if not path.exists():
        return []
    try:
        return load_raw_records(path)
    except (OSError, ValueError):
        return []


def _load_raw_response_if_present(path: Path) -> list[PaperRecord]:
    if not path.exists():
        return []
    try:
        return parse_crossref_payload(read_json(path))
    except (OSError, ValueError):
        return []


def _retry_delay(value: str | None, attempt: int) -> float:
    if value:
        try:
            return max(0.0, min(float(value), 30.0))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is not None:
                    return max(0.0, min((retry_at - datetime.now(UTC)).total_seconds(), 30.0))
            except (TypeError, ValueError, OverflowError):
                pass
    return 0.25 * (attempt + 1)
