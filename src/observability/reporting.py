from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write a concise, reproducible baseline report in Markdown."""
    lines = [
        "# Phase 1 Baseline Report",
        "",
        "## Source",
        f"- Source: {source_summary.get('source_api', 'Crossref REST API')}",
        f"- Records: {source_summary.get('records', 0)}",
        "",
        "## Evaluation Metrics",
        f"- Retrieval hit rate: {metrics.get('retrieval_hit_rate', 0):.4f}",
        f"- Mean token F1: {metrics.get('mean_token_f1', 0):.4f}",
        f"- Judge accuracy: {metrics.get('judge_accuracy', 0):.4f}",
        f"- Mean judge score: {metrics.get('mean_judge_score', 0):.4f}",
        f"- Samples: {metrics.get('samples', 0)}",
        "",
        "## Data Quality",
        f"- Quality gate: {'PASS' if quality.get('success') else 'FAIL'}",
        f"- Freshness: {'PASS' if freshness.get('is_fresh') else 'WARNING'}",
        f"- Stale rows: {freshness.get('stale_rows', 0)}/{freshness.get('total_rows', 0)}",
        f"- Latest published: {freshness.get('latest_published')}",
        f"- Oldest published: {freshness.get('oldest_published')}",
        "",
        "## Artifacts",
        "- Clean data: `data/clean/papers_clean.csv` and `papers_clean.json`",
        "- Vector store: `data/chroma/`",
        "- Benchmark: `data/eval/test_set.json`",
        "- Metrics: `data/results/baseline_metrics.json`",
    ]
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the three-state corruption and repair comparison report."""
    def metric_row(name: str, precision: int = 4) -> str:
        values = [baseline_metrics, corrupted_metrics, repaired_metrics]
        formatted = []
        for value in values:
            metric = value.get(name)
            formatted.append("N/A" if metric is None else f"{metric:.{precision}f}")
        return f"| `{name}` | {formatted[0]} | {formatted[1]} | {formatted[2]} |"

    lines = [
        "# Corruption and Repair Comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired |",
        "| --- | ---: | ---: | ---: |",
        metric_row("retrieval_hit_rate"),
        metric_row("mean_token_f1"),
        metric_row("judge_accuracy"),
        metric_row("mean_judge_score", 2),
        "",
        "## Quality and Freshness",
        "",
        "| Signal | Corrupted | Repaired |",
        "| --- | --- | --- |",
        f"| Quality gate | {'PASS' if corrupted_quality.get('success') else 'FAIL'} | {'PASS' if repaired_quality.get('success') else 'FAIL'} |",
        f"| Freshness | {'PASS' if corrupted_freshness.get('is_fresh') else 'WARNING'} | {'PASS' if repaired_freshness.get('is_fresh') else 'WARNING'} |",
        f"| Stale rows | {corrupted_freshness.get('stale_rows', 0)}/{corrupted_freshness.get('total_rows', 0)} | {repaired_freshness.get('stale_rows', 0)}/{repaired_freshness.get('total_rows', 0)} |",
        "",
        "## Interpretation",
        "",
        "- The corrupted dataset intentionally contains missing summaries, duplicate IDs, stale dates, truncated titles, and noisy embedding text.",
        "- The repaired dataset is rebuilt from the raw snapshot rather than patched in place.",
        "- The same benchmark test set is used in all three evaluations.",
    ]
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
