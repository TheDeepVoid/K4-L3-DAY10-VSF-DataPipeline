# Corruption and Repair Comparison

| Metric | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1.0000 | 0.2000 | 1.0000 |
| `mean_token_f1` | 0.3400 | 0.0000 | 0.3400 |
| `judge_accuracy` | 0.2000 | 0.0000 | 0.2000 |
| `mean_judge_score` | 2.00 | 1.20 | 2.00 |

## Quality and Freshness

| Signal | Corrupted | Repaired |
| --- | --- | --- |
| Quality gate | FAIL | PASS |
| Freshness | PASS | PASS |
| Stale rows | 2/24 | 1/24 |

## Interpretation

- The corrupted dataset intentionally contains missing summaries, duplicate IDs, stale dates, truncated titles, and noisy embedding text.
- The repaired dataset is rebuilt from the raw snapshot rather than patched in place.
- The same benchmark test set is used in all three evaluations.
