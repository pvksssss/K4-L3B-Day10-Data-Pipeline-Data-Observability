# CP0–CP3 Baseline Pipeline Design

## 1. Goal

Complete checkpoints CP0 through CP3 for the Day 10 data pipeline lab. The result must run end to end from the bundled Crossref snapshot, produce all baseline artifacts required by the rubric, and preserve the existing public function signatures and configured paths.

## 2. Scope

Included:

- Crossref payload parsing, API retrieval with retry, local fallback, and raw artifact persistence.
- Cleaning and pre-embedding data modeling.
- Great Expectations 1.x quality checks and freshness monitoring.
- A deterministic ten-question evaluation set covering four required question types.
- MiniLM embeddings and the `papers-baseline` ChromaDB collection.
- Baseline retrieval and answer evaluation.
- Baseline orchestration and Markdown reporting.
- Automated tests for the new behavior and an end-to-end offline run.

Excluded:

- CP4 corruption scenarios.
- CP5 repair and three-state comparison.
- Dashboard, CI, and other bonus work.
- Changes to report templates or team information that require student identities.

## 3. Constraints and Success Criteria

- Keep the existing signatures called by other modules.
- Use paths from `core.config`; do not hardcode machine-specific paths.
- Do not require network access for the default reproducible run.
- Do not require an LLM API key for baseline evaluation.
- Use Great Expectations 1.x APIs rather than legacy dataset APIs.
- Generate results from the pipeline rather than editing artifacts manually.
- CP3 is complete when `script/run_phase1.py` exits successfully and produces the clean data, embedding manifest and Chroma collection, evaluation set, metrics and answers, quality reports, freshness report, and phase-one Markdown report.

## 4. Architecture and Data Flow

```text
Crossref API or bundled snapshot
    -> parse_crossref_payload
    -> crossref_records.json
    -> build_clean_dataframe
    -> papers_clean.csv / papers_clean.json
    -> build_test_set
    -> test_set.json
    -> LocalEmbeddingIndex.build
    -> papers_embeddings.json + papers-baseline Chroma collection
    -> evaluate_pipeline
    -> baseline_metrics.json + baseline_answers.json
    -> run_data_quality_checks + build_freshness_report
    -> baseline_quality_report.json + freshness_report.json
    -> generate_phase1_report
    -> phase1_report.md
```

The orchestration layer coordinates these stages and does not duplicate their transformation logic.

## 5. CP0: Ingestion

### Payload parsing

`parse_crossref_payload` reads `payload["message"]["items"]` and maps valid items to `PaperRecord`.

- `paper_id`: normalized DOI; items without a DOI or title are skipped.
- `title`: first Crossref title value.
- `summary`: abstract with JATS/HTML tags removed and whitespace normalized.
- `authors`: display names formed from given and family names.
- `categories`: unique non-empty subjects in source order.
- `primary_category`: first category, or `Uncategorized`.
- `published` and `updated`: ISO dates selected from Crossref date parts with safe fallback.
- `abs_url`: canonical DOI URL.
- `pdf_url`: first link whose content type is PDF, otherwise empty.
- `comment`: publisher or container-title context when available.

### Fetch and fallback

`fetch_source_records` uses `https://api.crossref.org/works` with the configured query, filter, and row count. It supplies an identifying user agent and retries transient failures (`429`, `500`, `502`, `503`, `504`) with bounded exponential backoff.

The reproducible default prefers existing raw records when `REFRESH_SOURCE` is false. When refresh is requested, a successful response replaces both raw artifacts. If the request fails, the function falls back first to the existing raw response and then to the existing normalized records. It raises a clear error only when no usable source exists.

`load_raw_records` validates that the JSON payload is a list and converts each compatible object to `PaperRecord`.

## 6. CP1: Cleaning and Observability

### Clean schema

`build_clean_dataframe` produces these columns:

- `paper_id`, `title`, `summary`
- `authors`, `categories`, `primary_category`
- `published`, `updated`
- `abs_url`, `pdf_url`, `comment`
- `authors_joined`, `categories_joined`
- `summary_chars`, `age_days`
- `text_for_embedding`

Text fields have tags removed and whitespace normalized. Authors and categories are normalized as lists and joined using commas for scalar metadata. Dates use ISO `YYYY-MM-DD` strings. Invalid published dates, empty IDs, empty titles, and empty summaries are removed. Duplicate IDs keep the first normalized record. Output is deterministically sorted by publication date descending and then paper ID.

`text_for_embedding` contains five labeled parts: title, authors, published date, categories, and summary.

### Quality checks

`run_data_quality_checks` creates an ephemeral Great Expectations context and a pandas dataframe batch. It evaluates:

1. table row count between 1 and the configured maximum;
2. `paper_id` values not null;
3. `paper_id` values unique;
4. `title` values not null;
5. `summary` lengths between 20 and 20,000 characters.

The report stores overall success, each expectation result in a compact serializable form, row count, and freshness summary. Report routing uses the supplied report name, with baseline written to the configured baseline quality path.

### Freshness

Rows with `age_days > settings.freshness_threshold_days` are stale. The dataset is fresh when the stale ratio is at most 25%. The report includes latest and oldest publication dates, threshold, counts, ratio, and `is_fresh`.

Freshness remains an observability signal and contributes to the quality report's overall success without removing otherwise valid rows.

## 7. CP2: Evaluation Set and Vector Index

`build_test_set` requires enough valid rows to produce ten questions. It selects papers deterministically from the sorted clean dataframe so repeated runs use the same records.

The ten questions cover:

- three summary questions;
- three author questions;
- two publication-date questions;
- two category questions.

Each item contains `id`, `question_type`, `question`, `ground_truth`, and `ground_truth_doc_ids`. Questions quote the exact paper title so the existing QA layer can use exact lookup while retrieval metrics still record the ranked results.

The current `LocalEmbeddingIndex` remains the vector implementation. It rebuilds only the target baseline collection and writes a manifest that records its model, collection name, persistence path, and indexed documents.

## 8. CP3: Baseline Orchestration and Reporting

`pipelines.phase1.main` performs the following idempotent sequence:

1. load settings and ensure output directories exist through existing writers;
2. load existing raw records or fetch/fallback as defined in CP0;
3. build and persist the clean dataframe;
4. build or reuse the test set according to `REFRESH_TEST_SET`;
5. build the baseline vector index;
6. run evaluation using the shared test set;
7. run quality and freshness checks;
8. generate the Markdown report;
9. print a concise artifact and metric summary.

No API-backed agent demo is required for completion. Evaluation uses deterministic answer extraction. The judge already falls back to token-F1 heuristics if the configured LLM is unavailable, so missing credentials do not block the offline run.

The phase-one report contains source counts, artifact paths, evaluation metrics, the quality expectation table, freshness values, and a factual completion summary.

## 9. Error Handling

- Malformed Crossref payloads return no parsed records; orchestration rejects an empty source with a clear error.
- Network exceptions trigger local fallback.
- Empty or invalid clean data raises before embedding.
- A test set with fewer than ten constructible items raises a descriptive error.
- Quality reports remain serializable even if Great Expectations result objects change minor internal details.
- Report generation only claims values supplied by freshly generated artifacts.

## 10. Testing and Verification

Tests follow red-green-refactor and cover:

- Crossref parsing, raw record loading, fallback, and persistence.
- Cleaning normalization, date-derived fields, deduplication, filtering, and embedding text structure.
- Deterministic test-set size, type distribution, schema, and persistence.
- Quality pass/fail behavior and freshness boundary behavior.
- Markdown report contents.
- Offline phase-one orchestration with lightweight substitutes for the embedding/index boundary where necessary.

Final verification runs the complete test suite and the real offline `script/run_phase1.py`. Artifact contents are checked against the CP3 rubric rather than checking file existence alone.

## 11. Environment Strategy

The project declares Python `>=3.11,<3.14`, while the current global interpreter reports Python 3.14. The implementation does not broaden the supported range without evidence that all pinned libraries support it. Verification should use an available Python 3.11–3.13 interpreter or install one through the approved project tooling. If the compatible runtime or dependency installation is unavailable, code-level tests that do not require those dependencies still run and the exact environment blocker is reported.
