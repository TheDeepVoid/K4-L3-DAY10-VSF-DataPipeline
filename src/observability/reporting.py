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
    """TODO(student): viet markdown report so sanh baseline/corrupted/repaired."""
    raise NotImplementedError("Student task: implement corruption comparison report.")
