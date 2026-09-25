# Phase 1 Report - Baseline Data Pipeline

## 1. Source Summary

| Field | Value |
| :--- | :--- |
| Source | Crossref REST API |
| Mode | offline snapshot |
| Query | agentic retrieval augmented generation large language model |
| Max results requested | 24 |
| Records parsed | 24 |
| Clean rows | 24 |
| Embedding model | sentence-transformers/all-MiniLM-L6-v2 |
| Chroma collection | papers-baseline |
| Raw response | /home/aminix/Projects/K4A-DAY10-GroupXX-VSF/data/raw/crossref_response.json |
| Raw records | /home/aminix/Projects/K4A-DAY10-GroupXX-VSF/data/raw/crossref_records.json |

## 2. RAG Evaluation (Baseline)

| Metric | Value |
| :--- | :--- |
| Test samples | 10 |
| Retrieval Hit Rate | 100.0% |
| Mean Token F1 | 1.0000 |
| LLM Judge Accuracy | 100.0% |
| Mean LLM Judge Score | 5 |

### Ragas (optional pass)

```json
{'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'}
```

## 3. Data Quality Gate (Great Expectations 1.x)

- Engine: `great_expectations`
- GX version: `1.23.1`
- **Overall status: PASS**

| Check | Value |
| :--- | :--- |
| Rows | 24 |
| Duplicate paper_id | 0 |
| GX expectations | 6 |
| Failed expectations | 0 |

| Expectation | Column | Result |
| :--- | :--- | :--- |
| ExpectTableRowCountToBeBetween | - | PASS |
| ExpectColumnValuesToNotBeNull | paper_id | PASS |
| ExpectColumnValuesToBeUnique | paper_id | PASS |
| ExpectColumnValuesToNotBeNull | title | PASS |
| ExpectColumnValueLengthsToBeBetween | title | PASS |
| ExpectColumnValueLengthsToBeBetween | summary | PASS |

## 4. Freshness SLA

- Threshold: **180 days**
- Stale rows: **1 / 24** (4.2%)
- Allowed stale ratio: 25.0%
- **is_fresh: PASS**
- Latest published: `2026-07-22`
- Oldest published: `2026-03-28`

## 5. Conclusion

The baseline batch passed the Data Quality Gate and the Freshness SLA, so the clean corpus was indexed into ChromaDB and scored on the generated benchmark.
