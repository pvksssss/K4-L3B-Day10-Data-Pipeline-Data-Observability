from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest
import requests

from core.config import load_settings
from ingestion.crossref import PaperRecord, fetch_source_records, load_raw_records, parse_crossref_payload


def test_parse_crossref_payload_normalizes_valid_items():
    payload = {
        "message": {
            "items": [
                {
                    "DOI": " 10.1234/example ",
                    "title": ["  A   Crossref Paper  "],
                    "abstract": "<jats:p>First <b>important</b> result.\nSecond line.</jats:p>",
                    "author": [
                        {"given": "Ada", "family": "Lovelace"},
                        {"name": "Research Group"},
                    ],
                    "subject": [" Data Science ", " Machine Learning "],
                    "published": {"date-parts": [[2026, 4, 2]]},
                    "updated": {"date-parts": [[2026, 4, 3]]},
                    "URL": "https://doi.org/10.1234/example",
                    "link": [
                        {"URL": "https://example.org/article", "content-type": "text/html"},
                        {"URL": "https://example.org/article.pdf", "content-type": "application/pdf"},
                    ],
                }
            ]
        }
    }

    records = parse_crossref_payload(payload)

    assert records == [
        PaperRecord(
            paper_id="10.1234/example",
            title="A Crossref Paper",
            summary="First important result. Second line.",
            authors=["Ada Lovelace", "Research Group"],
            categories=["Data Science", "Machine Learning"],
            primary_category="Data Science",
            published="2026-04-02",
            updated="2026-04-03",
            abs_url="https://doi.org/10.1234/example",
            pdf_url="https://example.org/article.pdf",
            comment="Crossref record 10.1234/example",
        )
    ]


def test_parse_crossref_payload_skips_missing_identity_and_bad_dates():
    payload = {
        "message": {
            "items": [
                {"title": ["No DOI"], "published": {"date-parts": [[2026, 1, 1]]}},
                {"DOI": "10.1234/no-title", "published": {"date-parts": [[2026, 1, 1]]}},
                {"DOI": "10.1234/bad-date", "title": ["Invalid"], "published": {"date-parts": [[2026, 13, 1]]}},
                {"DOI": "10.1234/valid", "title": "Valid", "published": {"date-parts": [[2025]]}},
            ]
        }
    }

    records = parse_crossref_payload(payload)

    assert len(records) == 1
    assert records[0].paper_id == "10.1234/valid"
    assert records[0].published == "2025-01-01"
    assert records[0].updated == "2025-01-01"
    assert records[0].categories == []
    assert parse_crossref_payload({"message": {}}) == []
    assert parse_crossref_payload({"message": {"items": "bad"}}) == []


def test_load_raw_records_round_trips_records(tmp_path):
    record = PaperRecord(
        paper_id="10.1234/stored",
        title="Stored title",
        summary="Stored summary",
        authors=["A Author"],
        categories=["Science"],
        primary_category="Science",
        published="2026-01-01",
        updated="2026-01-02",
        abs_url="https://doi.org/10.1234/stored",
        pdf_url="https://example.org/stored.pdf",
        comment="Crossref record 10.1234/stored",
    )
    path = tmp_path / "records.json"
    path.write_text(json.dumps([asdict(record)]), encoding="utf-8")

    result = load_raw_records(path)

    assert result == [record]
    assert isinstance(result[0], PaperRecord)


def _payload(doi: str) -> dict:
    return {
        "message": {
            "items": [
                {
                    "DOI": doi,
                    "title": ["Fetched paper"],
                    "abstract": "<jats:p>Fetched summary.</jats:p>",
                    "published": {"date-parts": [[2026, 6, 5]]},
                    "URL": f"https://doi.org/{doi}",
                }
            ]
        }
    }


def _stored_record(doi: str) -> PaperRecord:
    return PaperRecord(
        paper_id=doi,
        title="Stored paper",
        summary="Stored summary",
        authors=[],
        categories=[],
        primary_category="",
        published="2026-01-01",
        updated="2026-01-01",
        abs_url=f"https://doi.org/{doi}",
        pdf_url=f"https://doi.org/{doi}",
        comment=f"Crossref record {doi}",
    )


class _Response:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_fetch_uses_existing_records_when_refresh_disabled(tmp_path, monkeypatch):
    settings = replace(load_settings(tmp_path), refresh_source=False)
    expected = _stored_record("10.1234/cached")
    settings.paths.raw_records_json.parent.mkdir(parents=True)
    settings.paths.raw_records_json.write_text(json.dumps([asdict(expected)]), encoding="utf-8")

    def unexpected_http(*args, **kwargs):
        raise AssertionError("cache should avoid HTTP")

    monkeypatch.setattr(requests.Session, "get", unexpected_http)

    assert fetch_source_records(settings) == [expected]
    assert json.loads(settings.paths.raw_records_json.read_text(encoding="utf-8")) == [asdict(expected)]
    assert not settings.paths.raw_api_response.exists()


def test_fetch_persists_successful_refresh(tmp_path, monkeypatch):
    settings = replace(load_settings(tmp_path), refresh_source=True, source_query="exact topic", source_filter="from-pub-date:2026-01-01", max_results=7)
    payload = _payload("10.1234/fetched")
    calls = []

    def get(self, url, **kwargs):
        calls.append((url, kwargs))
        return _Response(payload)

    monkeypatch.setattr(requests.Session, "get", get)

    records = fetch_source_records(settings)

    assert len(records) == 1
    assert records[0].paper_id == "10.1234/fetched"
    assert records[0].summary == "Fetched summary."
    assert json.loads(settings.paths.raw_api_response.read_text(encoding="utf-8")) == payload
    assert json.loads(settings.paths.raw_records_json.read_text(encoding="utf-8")) == [asdict(records[0])]
    assert calls[0][0] == "https://api.crossref.org/works"
    assert calls[0][1]["params"] == {"query": "exact topic", "filter": "from-pub-date:2026-01-01", "rows": 7}
    assert calls[0][1]["timeout"] > 0
    assert "User-Agent" in calls[0][1]["headers"]


def test_fetch_falls_back_to_raw_response_after_request_failure(tmp_path, monkeypatch):
    settings = replace(load_settings(tmp_path), refresh_source=True)
    payload = _payload("10.1234/raw-fallback")
    old_record = _stored_record("10.1234/older")
    settings.paths.raw_api_response.parent.mkdir(parents=True)
    settings.paths.raw_api_response.write_text(json.dumps(payload), encoding="utf-8")
    settings.paths.raw_records_json.write_text(json.dumps([asdict(old_record)]), encoding="utf-8")

    def fail_http(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests.Session, "get", fail_http)

    records = fetch_source_records(settings)

    assert [record.paper_id for record in records] == ["10.1234/raw-fallback"]
    assert json.loads(settings.paths.raw_api_response.read_text(encoding="utf-8")) == payload
    assert json.loads(settings.paths.raw_records_json.read_text(encoding="utf-8")) == [asdict(records[0])]


def test_fetch_retries_rate_limit_then_persists_success(tmp_path, monkeypatch):
    settings = replace(load_settings(tmp_path), refresh_source=True)
    responses = [
        _Response({}, status_code=429, headers={"Retry-After": "0"}),
        _Response(_payload("10.1234/recovered")),
    ]

    def get(self, url, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(requests.Session, "get", get)

    records = fetch_source_records(settings)

    assert [record.paper_id for record in records] == ["10.1234/recovered"]
    assert responses == []
    assert json.loads(settings.paths.raw_records_json.read_text(encoding="utf-8")) == [asdict(records[0])]


def test_fetch_does_not_retry_non_transient_http_error(tmp_path, monkeypatch):
    settings = replace(load_settings(tmp_path), refresh_source=True)
    calls = []

    def get(self, url, **kwargs):
        calls.append(url)
        return _Response({}, status_code=404)

    monkeypatch.setattr(requests.Session, "get", get)

    with pytest.raises(RuntimeError, match="no usable local snapshot"):
        fetch_source_records(settings)

    assert len(calls) == 1
