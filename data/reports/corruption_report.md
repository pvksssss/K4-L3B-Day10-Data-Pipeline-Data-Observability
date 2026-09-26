# Data Pipeline & Observability: 3-State Comparison Report

> **Pipeline Stages:** Baseline (Clean) ➔ Synthetic Corruption (Silent Failure) ➔ Idempotent Repair (Self-healing)

## 1. Executive Summary & Metric Comparison Table

| Metric / Indicator | Baseline (Clean) | Corrupted (Dirty) | Repaired (Restored) | Impact & Recovery |
| :--- | :---: | :---: | :---: | :--- |
| **Retrieval Hit Rate** | 1.000 | 0.600 | 1.000 | Severe drop -> 100% recovered |
| **Mean Token F1** | 1.000 | 0.651 | 1.000 | Degradation in dirty data recovered |
| **Judge Accuracy** | 1.000 | 0.700 | 1.000 | Answer faithfulness restored |
| **Mean Judge Score (1-5)** | 5.000 | 3.400 | 5.000 | Model answer quality recovered |
| **Data Quality Gate (GX 1.x)** | PASS | FAIL | PASS | Caught corrupt schema violations |
| **Freshness SLA Status** | PASS | FAIL | PASS | Flagged stale articles (>25% stale) |

## 2. Synthetic Corruption Analysis (Silent Failure Demonstration)

Six synthetic corruption scenarios were injected to simulate real-world upstream data issues:
1. **Drop Latest Records (20%):** Caused immediate recall failure for recent benchmark questions.
2. **Blank Summary:** Triggered Great Expectations `expect_column_value_lengths_to_be_between` failure.
3. **Noise Injection:** Destroyed semantic embedding representations and dropped cosine similarity rankings.
4. **Truncated Titles (<8 chars):** Broke exact matching and damaged retrieval precision.
5. **Stale Dates (Shifted -400 days):** Breached Freshness SLA threshold (stale ratio > 25%).
6. **Duplicate Records:** Triggered GX `expect_column_values_to_be_unique` constraint violation.

## 3. Idempotent Repair & Self-Healing Verification

- **Raw Source Lineage:** Repaired dataframe is rebuilt deterministically from authoritative raw snapshot `data/raw/crossref_records.json`.
- **Vector Store Reindexing:** Rebuilt isolated collection `papers-repaired` to avoid vector space contamination.
- **Recovery Benchmark:** Re-evaluated on the exact same 10-question test set, proving 100% metrics recovery without manual data patching.

## 4. Quality Gate & Freshness Findings

### Corrupted State Quality Checks:
- Overall Status: FAIL
- GX Status: FAIL
- Freshness Status: FAIL (Stale ratio: 0.381)

### Repaired State Quality Checks:
- Overall Status: PASS
- GX Status: PASS
- Freshness Status: PASS (Stale ratio: 0.042)
