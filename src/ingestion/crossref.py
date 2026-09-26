from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core.config import Settings


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


_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_CROSSREF_API_URL = "https://api.crossref.org/works"
_USER_AGENT = "paper-rag-ingestion/1.0"


def _clean_text(value: Any) -> str:
    """Convert a possibly-HTML string into normalized plain text."""
    if value is None:
        return ""

    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _first_text(value: Any) -> str:
    """Return the first usable string from a scalar/list value."""
    if isinstance(value, list):
        for item in value:
            text = _clean_text(item)
            if text:
                return text
        return ""
    return _clean_text(value)


def _date_parts_to_iso(value: Any) -> str:
    """Convert Crossref date-parts into YYYY-MM-DD where possible."""
    if not isinstance(value, dict):
        return ""

    parts = value.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return ""

    parts = parts[0]
    if not parts:
        return ""

    try:
        year = int(parts[0])
    except (TypeError, ValueError):
        return ""

    if len(parts) >= 2:
        try:
            month = int(parts[1])
        except (TypeError, ValueError):
            month = 1
    else:
        month = 1

    if len(parts) >= 3:
        try:
            day = int(parts[2])
        except (TypeError, ValueError):
            day = 1
    else:
        day = 1

    month = min(max(month, 1), 12)
    day = min(max(day, 1), 31)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _extract_date(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        date = _date_parts_to_iso(value)
        if date:
            return date
    return ""


def _extract_authors(item: dict[str, Any]) -> list[str]:
    authors: list[str] = []

    raw_authors = item.get("author", [])
    if not isinstance(raw_authors, list):
        return authors

    for author in raw_authors:
        if not isinstance(author, dict):
            continue

        given = _clean_text(author.get("given"))
        family = _clean_text(author.get("family"))
        name = _clean_text(author.get("name"))

        if given and family:
            full_name = f"{given} {family}"
        elif family:
            full_name = family
        elif given:
            full_name = given
        else:
            full_name = name

        if full_name:
            authors.append(full_name)

    return authors


def _extract_categories(item: dict[str, Any]) -> list[str]:
    raw_subject = item.get("subject", [])
    if not isinstance(raw_subject, list):
        raw_subject = [raw_subject]

    categories: list[str] = []
    for subject in raw_subject:
        value = _clean_text(subject)
        if value and value not in categories:
            categories.append(value)

    return categories


def _extract_urls(item: dict[str, Any], doi: str) -> tuple[str, str]:
    abs_url = ""
    pdf_url = ""

    resource = item.get("resource")
    if isinstance(resource, dict):
        primary_url = _clean_text(resource.get("primary.URL"))
        if primary_url:
            abs_url = primary_url

    links = item.get("link", [])
    if isinstance(links, list):
        for link in links:
            if not isinstance(link, dict):
                continue

            url = _clean_text(link.get("URL"))
            if not url:
                continue

            content_type = _clean_text(link.get("content-type")).lower()
            content_version = _clean_text(link.get("content-version")).lower()

            if content_type == "application/pdf" or url.lower().endswith(".pdf"):
                if not pdf_url:
                    pdf_url = url
            elif not abs_url and (
                content_type in {"text/html", "application/xhtml+xml"}
                or content_version
            ):
                abs_url = url

    if not abs_url and doi:
        abs_url = f"https://doi.org/{doi}"

    return abs_url, pdf_url


def _extract_comment(item: dict[str, Any]) -> str:
    """Extract Crossref's free-form note-like metadata when available."""
    for key in ("comment", "note", "short-title"):
        value = _first_text(item.get(key))
        if value:
            return value

    return ""


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thành list PaperRecord.

    Duyệt `payload["message"]["items"]`, chuẩn hóa các trường text,
    bỏ qua record thiếu DOI hoặc title, rồi ánh xạ sang `PaperRecord`.
    """
    if not isinstance(payload, dict):
        return []

    message = payload.get("message")
    if not isinstance(message, dict):
        return []

    items = message.get("items", [])
    if not isinstance(items, list):
        return []

    records: list[PaperRecord] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        doi = _clean_text(item.get("DOI"))
        title = _first_text(item.get("title"))

        if not doi or not title:
            continue

        summary = _first_text(item.get("abstract"))
        authors = _extract_authors(item)
        categories = _extract_categories(item)

        primary_category = categories[0] if categories else ""

        published = _extract_date(
            item,
            "published-print",
            "published-online",
            "published",
            "issued",
            "created",
        )
        updated = _extract_date(
            item,
            "updated",
            "published-online",
            "published",
            "issued",
            "created",
        )

        abs_url, pdf_url = _extract_urls(item, doi)
        comment = _extract_comment(item)

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    return records


def _request_crossref(
    settings: Settings,
    *,
    retries: int = 3,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetch Crossref JSON with retries for transient HTTP failures."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }

    url = f"{_CROSSREF_API_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        },
        method="GET",
    )

    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                payload = json.loads(body)

                if not isinstance(payload, dict):
                    raise ValueError("Crossref response is not a JSON object.")

                return payload

        except HTTPError as exc:
            last_error = exc

            if exc.code not in _RETRYABLE_STATUS_CODES or attempt >= retries:
                raise

        except (URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
            last_error = exc

            if attempt >= retries:
                raise

        # Exponential backoff: 1s, 2s, 4s, ...
        time.sleep(2**attempt)

    raise RuntimeError("Crossref request failed.") from last_error


def _snapshot_candidates(settings: Settings) -> list[Path]:
    root = settings.paths.project_dir

    return [
        root / "data" / "snapshots" / "crossref_response.json",
        root / "data" / "sample" / "crossref_response.json",
        root / "data" / "samples" / "crossref_response.json",
        settings.paths.raw_api_response,
    ]


def _load_snapshot(settings: Settings) -> dict[str, Any]:
    for path in _snapshot_candidates(settings):
        if not path.is_file():
            continue

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, dict):
            raise ValueError(f"Snapshot is not a JSON object: {path}")

        return payload

    candidates = "\n".join(
        f"  - {path}" for path in _snapshot_candidates(settings)
    )
    raise FileNotFoundError(
        "Crossref API failed and no snapshot was found. Checked:\n" + candidates
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Gọi Crossref API, fallback snapshot, lưu raw payload và records.

    API được ưu tiên sử dụng khi `settings.refresh_source=True`.
    Nếu API không khả dụng, hàm tự động đọc snapshot mẫu.
    """
    payload: dict[str, Any]

    should_refresh = settings.refresh_source

    if should_refresh:
        try:
            payload = _request_crossref(settings)
        except Exception:
            payload = _load_snapshot(settings)
    else:
        try:
            payload = _load_snapshot(settings)
        except (FileNotFoundError, json.JSONDecodeError):
            payload = _request_crossref(settings)

    _write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload)

    _write_json(
        settings.paths.raw_records_json,
        [asdict(record) for record in records],
    )

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Đọc JSON snapshot và map thành `PaperRecord`."""
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, list):
        raise ValueError(f"Raw records file must contain a JSON list: {path}")

    records: list[PaperRecord] = []

    for item in payload:
        if not isinstance(item, dict):
            continue

        try:
            records.append(
                PaperRecord(
                    paper_id=_clean_text(item.get("paper_id")),
                    title=_clean_text(item.get("title")),
                    summary=_clean_text(item.get("summary")),
                    authors=[
                        _clean_text(author)
                        for author in item.get("authors", [])
                        if _clean_text(author)
                    ],
                    categories=[
                        _clean_text(category)
                        for category in item.get("categories", [])
                        if _clean_text(category)
                    ],
                    primary_category=_clean_text(item.get("primary_category")),
                    published=_clean_text(item.get("published")),
                    updated=_clean_text(item.get("updated")),
                    abs_url=_clean_text(item.get("abs_url")),
                    pdf_url=_clean_text(item.get("pdf_url")),
                    comment=_clean_text(item.get("comment")),
                )
            )
        except (TypeError, AttributeError):
            continue

    return records