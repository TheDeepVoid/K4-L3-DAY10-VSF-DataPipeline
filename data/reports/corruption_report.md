# Corruption & Idempotent Repair Report

## 1. Three-State Comparison

| Metric | Baseline | Corrupted | Repaired |
| :--- | :--- | :--- | :--- |
| Test samples | 10 | 10 | 10 |
| Retrieval Hit Rate | 100.0% | 50.0% | 100.0% |
| Mean Token F1 | 1.0000 | 0.7788 | 1.0000 |
| LLM Judge Accuracy | 100.0% | 80.0% | 100.0% |
| Mean LLM Judge Score | 5.0000 | 4.1000 | 5.0000 |
| Data Quality Gate | PASS | FAIL | PASS |
| Duplicate paper_id | 0 | 2 | 0 |
| Freshness SLA (is_fresh) | PASS | FAIL | PASS |
| Stale ratio | 4.2% | 42.9% | 4.2% |

## 2. Degradation Analysis (Corrupted vs Baseline)

| Metric | Delta |
| :--- | :--- |
| Retrieval Hit Rate | -0.5000 |
| Mean Token F1 | -0.2212 |
| LLM Judge Accuracy | -0.2000 |

### Expectations that caught the corruption

- `ExpectTableRowCountToBeBetween`
- `ExpectColumnValuesToBeUnique` (column=paper_id)
- `ExpectColumnValueLengthsToBeBetween` (column=title)
- `ExpectColumnValueLengthsToBeBetween` (column=summary)

### Freshness alert

> Freshness SLA breached: 42.9% of rows are older than 180 days (limit 25%).

## 3. Repair Verification

The repaired state is rebuilt from the immutable raw snapshot (`data/raw/crossref_records.json`) by re-running cleaning, the Data Quality Gate, the Freshness SLA, the ChromaDB index and the evaluation set. Re-running this flow any number of times yields the same clean dataset, which demonstrates idempotency.

- Repaired gate status: **PASS**
- Repaired freshness: **PASS**
