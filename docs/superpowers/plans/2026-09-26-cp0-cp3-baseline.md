# CP0–CP3 Baseline Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the complete offline-capable Crossref baseline pipeline required by checkpoints CP0 through CP3.

**Architecture:** Keep each transformation in its existing module and use `pipelines.phase1.main` only for orchestration. Persist every stage through configured artifact paths so tests, reports, and later corruption work consume the same contracts.

**Tech Stack:** Python 3.11–3.13, pandas, requests, Great Expectations 1.x, sentence-transformers MiniLM, ChromaDB, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-cp0-cp3-baseline-design.md`

## Global Constraints

- Preserve all existing public function signatures and configured artifact paths.
- Do not hardcode machine-specific paths or secrets.
- The default run must work from the bundled snapshot without network access.
- Baseline evaluation must not require an LLM API key.
- Use Great Expectations 1.x APIs, not legacy dataset APIs.
- Generate all metrics and reports from pipeline outputs.
- Support Python `>=3.11,<3.14` as declared in `pyproject.toml`.

## Review Focus

- A Crossref item with malformed or missing date parts must be skipped or safely normalized without aborting the batch; Task 1 tests this.
- An API refresh failure must preserve and use a valid local snapshot; Task 1 tests this.
- Mixed list/string/null values in raw author and category fields must normalize deterministically; Task 2 tests this.
- Great Expectations result objects must be reduced to stable JSON-safe data rather than dumping internal objects; Task 4 tests report serialization.
- A rerun with existing artifacts must remain deterministic and replace only the baseline Chroma collection; Task 6 tests the repeated offline run.

---

### Task 1: Crossref ingestion and offline fallback

**Files:**
- Create: `tests/test_crossref.py`
- Modify: `src/ingestion/crossref.py`

**Interfaces:**
- Consumes: `Settings`, `Paths`, Crossref JSON payloads.
- Produces: `parse_crossref_payload(payload: dict) -> list[PaperRecord]`, `fetch_source_records(settings: Settings) -> list[PaperRecord]`, `load_raw_records(path: Path) -> list[PaperRecord]`.

- [ ] **Step 1: Write failing parser and loader tests**

Add tests named `test_parse_crossref_payload_normalizes_valid_items`, `test_parse_crossref_payload_skips_missing_identity_and_bad_dates`, and `test_load_raw_records_round_trips_records`. Assert DOI/title identity, tag-free summaries, author/category extraction, ISO dates, PDF selection, invalid-row handling, and dataclass reconstruction.

- [ ] **Step 2: Run parser tests and verify RED**

Run: `python -m pytest tests/test_crossref.py -k "parse or load" -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 3: Implement parsing and raw loading**

Add focused private helpers for scalar/list normalization, tag stripping, date-part conversion, author formatting, and record serialization. Keep malformed payload behavior deterministic and return an empty list when `message.items` is absent.

- [ ] **Step 4: Run parser tests and verify GREEN**

Run: `python -m pytest tests/test_crossref.py -k "parse or load" -v`

Expected: all selected tests PASS.

- [ ] **Step 5: Write failing fetch/fallback tests**

Add `test_fetch_uses_existing_records_when_refresh_disabled`, `test_fetch_persists_successful_refresh`, and `test_fetch_falls_back_to_raw_response_after_request_failure`. Use a temporary project configuration and replace only the HTTP boundary; assert both artifact contents and returned records.

- [ ] **Step 6: Run fetch tests and verify RED**

Run: `python -m pytest tests/test_crossref.py -k fetch -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 7: Implement fetch, retry, persistence, and fallback**

Use `requests.Session.get` with the configured query/filter/rows, a bounded retry loop for `429/500/502/503/504`, `Retry-After` support, timeout, and a descriptive user agent. Prefer existing normalized records when refresh is disabled; on refresh failure parse the raw response before falling back to normalized records.

- [ ] **Step 8: Run ingestion tests**

Run: `python -m pytest tests/test_crossref.py -v`

Expected: all tests PASS.

- [ ] **Step 9: Commit ingestion**

```bash
git add tests/test_crossref.py src/ingestion/crossref.py
git commit -m "feat: implement Crossref ingestion and fallback"
```

### Task 2: Cleaning and pre-embedding data model

**Files:**
- Create: `tests/test_cleaning.py`
- Modify: `src/ingestion/cleaning.py`

**Interfaces:**
- Consumes: `list[PaperRecord]`, timezone-aware or naive `datetime` run date.
- Produces: `build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame` with the schema defined in the spec.

- [ ] **Step 1: Write failing cleaning-contract tests**

Add `test_build_clean_dataframe_normalizes_schema_and_embedding_text`, `test_build_clean_dataframe_deduplicates_and_filters_invalid_rows`, and `test_build_clean_dataframe_normalizes_mixed_collection_values`. Assert exact column order, five labeled embedding sections, normalized lists and strings, ISO dates, `summary_chars`, `age_days`, stable ordering, and one row per DOI.

- [ ] **Step 2: Run cleaning tests and verify RED**

Run: `python -m pytest tests/test_cleaning.py -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 3: Implement dataframe construction**

Normalize text without altering source identity, parse dates with pandas, reject unusable rows, calculate age from normalized dates, build helper columns, deduplicate before sorting, and return a dataframe with a fixed column list even for empty input.

- [ ] **Step 4: Run cleaning tests and verify GREEN**

Run: `python -m pytest tests/test_cleaning.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit cleaning**

```bash
git add tests/test_cleaning.py src/ingestion/cleaning.py
git commit -m "feat: build clean paper dataframe"
```

### Task 3: Deterministic evaluation test set

**Files:**
- Create: `tests/test_testset.py`
- Modify: `src/evaluation/testset.py`

**Interfaces:**
- Consumes: clean dataframe from Task 2 and an output path.
- Produces: `build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]` with ten persisted items.

- [ ] **Step 1: Write failing test-set tests**

Add `test_build_test_set_writes_ten_questions_with_required_distribution`, `test_build_test_set_is_deterministic`, and `test_build_test_set_rejects_insufficient_rows`. Assert a `3/3/2/2` distribution for summary/authors/date/categories, sequential stable IDs, exact ground-truth document IDs, quoted titles, JSON equality, repeatability, and a descriptive `ValueError` when fewer than ten valid rows exist.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_testset.py -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 3: Implement deterministic selection and persistence**

Select ten rows from the normalized dataframe in stable order, map question types using the required distribution, derive ground truth from the matching clean columns, and persist via `write_json`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/test_testset.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit test-set builder**

```bash
git add tests/test_testset.py src/evaluation/testset.py
git commit -m "feat: generate deterministic evaluation set"
```

### Task 4: Great Expectations quality gate and freshness

**Files:**
- Create: `tests/test_quality.py`
- Modify: `src/observability/quality.py`

**Interfaces:**
- Consumes: clean dataframe and `Settings`.
- Produces: `run_data_quality_checks(...) -> dict[str, Any]` and `build_freshness_report(...) -> dict[str, Any]`, both persisted as JSON.

- [ ] **Step 1: Write failing freshness tests**

Add `test_freshness_passes_at_twenty_five_percent_stale`, `test_freshness_fails_above_twenty_five_percent_stale`, and `test_freshness_handles_empty_dataframe`. Assert the strict `age_days > threshold` rule, boundary ratio, dates, counts, JSON-safe output, and an explicit non-fresh empty result.

- [ ] **Step 2: Run freshness tests and verify RED**

Run: `python -m pytest tests/test_quality.py -k freshness -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 3: Implement freshness reporting**

Compute from `age_days` and normalized `published`; write only Python scalar/list/dict values through `write_json`.

- [ ] **Step 4: Run freshness tests and verify GREEN**

Run: `python -m pytest tests/test_quality.py -k freshness -v`

Expected: selected tests PASS.

- [ ] **Step 5: Write failing GX quality tests**

Add `test_quality_gate_passes_valid_dataframe_and_writes_report`, `test_quality_gate_fails_duplicate_and_short_summary`, and `test_quality_report_is_json_serializable`. Assert expectation types, individual success values, freshness integration, report routing, and successful `json.dumps`.

- [ ] **Step 6: Run GX tests and verify RED**

Run: `python -m pytest tests/test_quality.py -k quality -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 7: Implement the GX 1.x ephemeral batch and compact result mapping**

Use `gx.get_context(mode="ephemeral")`, a pandas data source, dataframe asset, whole-dataframe batch definition, and the expectation classes named in the rubric. Combine GX and freshness success and route `baseline`, `corrupted`, or other report names to deterministic paths under `data/quality`.

- [ ] **Step 8: Run quality tests**

Run: `python -m pytest tests/test_quality.py -v`

Expected: all tests PASS with no serialization error.

- [ ] **Step 9: Commit observability**

```bash
git add tests/test_quality.py src/observability/quality.py
git commit -m "feat: add GX quality and freshness checks"
```

### Task 5: Phase-one Markdown reporting

**Files:**
- Create: `tests/test_reporting.py`
- Modify: `src/observability/reporting.py`

**Interfaces:**
- Consumes: source summary, evaluation metrics, quality payload, freshness payload.
- Produces: `generate_phase1_report(...) -> None` writing the configured Markdown artifact.

- [ ] **Step 1: Write failing report test**

Add `test_generate_phase1_report_contains_source_metrics_quality_and_freshness`. Supply representative dictionaries and assert the report contains the record count, all four baseline metrics, expectation names/statuses, freshness ratio/status, and no placeholder text.

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/test_reporting.py -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 3: Implement report rendering**

Build Markdown using small formatting helpers, stable numeric precision, and `write_text`. Leave `generate_corruption_report` for CP4–CP5.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/test_reporting.py -v`

Expected: test PASS.

- [ ] **Step 5: Commit reporting**

```bash
git add tests/test_reporting.py src/observability/reporting.py
git commit -m "feat: generate phase one report"
```

### Task 6: CP3 orchestration, offline run, and artifact verification

**Files:**
- Create: `tests/test_phase1.py`
- Modify: `src/pipelines/phase1.py`
- Modify only if required by integration evidence: `src/evaluation/metrics.py`
- Modify only if required by integration evidence: `src/retrieval/index.py`

**Interfaces:**
- Consumes: all Task 1–5 interfaces plus existing `LocalEmbeddingIndex.build` and `evaluate_pipeline`.
- Produces: `pipelines.phase1.main() -> None` and the complete CP3 artifact set.

- [ ] **Step 1: Write failing orchestration test**

Add `test_phase1_main_runs_stages_in_order_and_persists_contracts`. Use a temporary project root and lightweight substitutes only at the embedding/index and evaluator boundaries. Assert clean CSV/JSON, test set, embedding manifest, metrics, answers, quality, freshness, and Markdown report paths contain data from the same run.

- [ ] **Step 2: Run orchestration test and verify RED**

Run: `python -m pytest tests/test_phase1.py -v`

Expected: FAIL at the existing `NotImplementedError`.

- [ ] **Step 3: Implement `pipelines.phase1.main`**

Load settings, resolve the raw source, validate non-empty inputs and clean data, persist dataframe records in consistent JSON orientation, build or reuse the test set according to `refresh_test_set`, build/evaluate the index, run quality/freshness, generate the report, and print a concise summary.

- [ ] **Step 4: Run orchestration test and verify GREEN**

Run: `python -m pytest tests/test_phase1.py -v`

Expected: test PASS.

- [ ] **Step 5: Run the full automated suite**

Run: `python -m pytest -v`

Expected: all tests PASS, zero failures.

- [ ] **Step 6: Prepare a compatible project environment**

Use Python 3.11–3.13 and install the locked/project dependencies. Do not change the declared Python range merely to accommodate the current global Python 3.14 interpreter.

- [ ] **Step 7: Run the real offline CP3 pipeline twice**

Run: `python script/run_phase1.py` twice with `REFRESH_SOURCE=false`, `REFRESH_TEST_SET=false`, and `LLM_PROVIDER=mock`.

Expected on both runs: exit code 0, 24 clean records, 10 evaluation samples, the `papers-baseline` collection rebuilt without duplication, baseline quality success, and a fresh status under the documented SLA.

- [ ] **Step 8: Verify artifact contents against the rubric**

Inspect:

- `data/clean/papers_clean.csv` and `papers_clean.json` for 24 unique rows and required columns;
- `data/embeddings/papers_embeddings.json` for model, collection, and 24 documents;
- `data/eval/test_set.json` for ten questions and all four types;
- `data/results/baseline_metrics.json` and `baseline_answers.json` for ten samples and required metrics;
- `data/quality/baseline_quality_report.json` and `freshness_report.json` for GX checks and SLA evidence;
- `data/reports/phase1_report.md` for values matching the generated JSON artifacts;
- ChromaDB collection `papers-baseline` for exactly 24 indexed documents.

- [ ] **Step 9: Run repository safety checks**

Run: `git diff --check`, `git status --short`, and a tracked-file scan for `.env` or credential values.

Expected: no whitespace errors, no tracked `.env`, and only intended source/test/artifact changes.

- [ ] **Step 10: Commit orchestration and verified artifacts**

```bash
git add tests/test_phase1.py src/pipelines/phase1.py src/evaluation/metrics.py src/retrieval/index.py data/clean data/embeddings data/eval data/results/baseline_metrics.json data/results/baseline_answers.json data/quality data/reports/phase1_report.md
git commit -m "feat: complete CP3 baseline pipeline"
```
