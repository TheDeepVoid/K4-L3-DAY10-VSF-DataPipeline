# Phase 1 Baseline Report

## Source
- Source: Crossref REST API
- Records: 24

## Evaluation Metrics
- Retrieval hit rate: 1.0000
- Mean token F1: 0.3400
- Judge accuracy: 0.2000
- Mean judge score: 2.0000
- Samples: 5

## Data Quality
- Quality gate: PASS
- Freshness: PASS
- Stale rows: 1/24
- Latest published: 2026-07-22
- Oldest published: 2026-03-28

## Artifacts
- Clean data: `data/clean/papers_clean.csv` and `papers_clean.json`
- Vector store: `data/chroma/`
- Benchmark: `data/eval/test_set.json`
- Metrics: `data/results/baseline_metrics.json`
