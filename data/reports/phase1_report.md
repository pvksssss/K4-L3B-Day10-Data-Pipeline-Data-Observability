# Phase-one baseline report

## Source and artifacts

- Source: Crossref REST API
- Raw records: 24
- Clean records: 24
- raw_records_path: `data/raw/crossref_records.json`
- clean_csv_path: `data/clean/papers_clean.csv`
- clean_json_path: `data/clean/papers_clean.json`
- embeddings_path: `data/embeddings/papers_embeddings.json`
- test_set_path: `data/eval/test_set.json`
- metrics_path: `data/results/baseline_metrics.json`
- answers_path: `data/results/baseline_answers.json`
- quality_path: `data/quality/baseline_quality_report.json`
- freshness_path: `data/quality/freshness_report.json`

## Baseline evaluation

- Samples: 10
- retrieval_hit_rate: 1.000
- mean_token_f1: 1.000
- judge_accuracy: 1.000
- mean_judge_score: 5.000

## Data quality

- Overall: PASS
- Great Expectations: PASS
- expect_table_row_count_to_be_between: PASS
- expect_column_values_to_not_be_null (paper_id): PASS
- expect_column_values_to_be_unique (paper_id): PASS
- expect_column_values_to_not_be_null (title): PASS
- expect_column_value_lengths_to_be_between (summary): PASS

## Freshness

- Status: PASS
- Stale rows: 1 / 24
- Stale ratio: 0.042
- Threshold days: 180
- oldest_published: 2026-03-28
- latest_published: 2026-07-22
