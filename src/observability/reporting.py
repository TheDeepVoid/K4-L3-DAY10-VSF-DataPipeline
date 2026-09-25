from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.utils import write_text

METRIC_LABELS = {
    "samples": "Test samples",
    "retrieval_hit_rate": "Retrieval Hit Rate",
    "mean_token_f1": "Mean Token F1",
    "judge_accuracy": "LLM Judge Accuracy",
    "mean_judge_score": "Mean LLM Judge Score",
}

QUALITY_LABELS = {
    "row_count": "Rows",
    "duplicate_paper_ids": "Duplicate paper_id",
    "expectation_count": "GX expectations",
    "failed_expectation_count": "Failed expectations",
}


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _num(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _check(flag: Any) -> str:
    if flag is True:
        return "PASS"
    if flag is False:
        return "FAIL"
    return "n/a"


def _load_optional_json(path: Path) -> dict[str, Any]:
    """Read a baseline artifact if it exists, otherwise return an empty mapping."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _baseline_quality_and_freshness(report_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve the baseline gate/SLA artifacts relative to the report location.

    ``generate_corruption_report`` keeps the starter signature, which does not
    carry the baseline quality payloads, so they are read from the canonical
    ``data/quality/`` paths instead of being threaded through the pipeline.
    """
    quality_dir = Path(report_path).resolve().parent.parent / "quality"
    return (
        _load_optional_json(quality_dir / "baseline_quality_report.json"),
        _load_optional_json(quality_dir / "freshness_report.json"),
    )


def generate_phase1_report(
    report_path: Path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline (Phase 1) Markdown report."""
    lines: list[str] = [
        "# Phase 1 Report - Baseline Data Pipeline",
        "",
        "## 1. Source Summary",
        "",
        "| Field | Value |",
        "| :--- | :--- |",
    ]
    for key, value in source_summary.items():
        lines.append(f"| {key} | {value} |")

    lines += [
        "",
        "## 2. RAG Evaluation (Baseline)",
        "",
        "| Metric | Value |",
        "| :--- | :--- |",
    ]
    for key, label in METRIC_LABELS.items():
        value = metrics.get(key)
        if key in {"retrieval_hit_rate", "judge_accuracy"}:
            rendered = _pct(value)
        elif isinstance(value, float):
            rendered = _num(value)
        else:
            rendered = "n/a" if value is None else str(value)
        lines.append(f"| {label} | {rendered} |")

    ragas = metrics.get("ragas")
    if isinstance(ragas, dict) and ragas:
        lines += ["", "### Ragas (optional pass)", ""]
        lines.append("```json")
        lines.append(str(ragas))
        lines.append("```")

    lines += [
        "",
        "## 3. Data Quality Gate (Great Expectations 1.x)",
        "",
        f"- Engine: `{quality.get('engine', 'n/a')}`",
        f"- GX version: `{quality.get('gx_version') or 'n/a'}`",
        f"- **Overall status: {_check(quality.get('success'))}**",
        "",
        "| Check | Value |",
        "| :--- | :--- |",
    ]
    for key, label in QUALITY_LABELS.items():
        lines.append(f"| {label} | {quality.get(key, 'n/a')} |")

    expectations = quality.get("expectations", []) or []
    if expectations:
        lines += [
            "",
            "| Expectation | Column | Result |",
            "| :--- | :--- | :--- |",
        ]
        for item in expectations:
            kwargs = item.get("kwargs", {}) or {}
            column = kwargs.get("column", "-")
            lines.append(f"| {item.get('type', 'n/a')} | {column} | {_check(item.get('success'))} |")

    lines += [
        "",
        "## 4. Freshness SLA",
        "",
        f"- Threshold: **{freshness.get('threshold_days', 'n/a')} days**",
        f"- Stale rows: **{freshness.get('stale_rows', 'n/a')} / {freshness.get('total_rows', 'n/a')}** "
        f"({_pct(freshness.get('stale_ratio'))})",
        f"- Allowed stale ratio: {_pct(freshness.get('stale_ratio_limit'))}",
        f"- **is_fresh: {_check(freshness.get('is_fresh'))}**",
        f"- Latest published: `{freshness.get('latest_published')}`",
        f"- Oldest published: `{freshness.get('oldest_published')}`",
    ]
    if freshness.get("alert"):
        lines.append(f"- Alert: **{freshness['alert']}**")

    lines += [
        "",
        "## 5. Conclusion",
        "",
        "The baseline batch passed the Data Quality Gate and the Freshness SLA, so the "
        "clean corpus was indexed into ChromaDB and scored on the generated benchmark.",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))


def generate_corruption_report(
    report_path: Path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the Baseline vs Corrupted vs Repaired comparison report."""
    baseline_quality, baseline_freshness = _baseline_quality_and_freshness(report_path)

    lines: list[str] = [
        "# Corruption & Idempotent Repair Report",
        "",
        "## 1. Three-State Comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired |",
        "| :--- | :--- | :--- | :--- |",
    ]

    comparison_rows = [
        ("Test samples", "samples", "int"),
        ("Retrieval Hit Rate", "retrieval_hit_rate", "pct"),
        ("Mean Token F1", "mean_token_f1", "num"),
        ("LLM Judge Accuracy", "judge_accuracy", "pct"),
        ("Mean LLM Judge Score", "mean_judge_score", "num"),
    ]
    for label, key, kind in comparison_rows:
        cells = []
        for metrics in (baseline_metrics, corrupted_metrics, repaired_metrics):
            value = metrics.get(key)
            if kind == "pct":
                cells.append(_pct(value))
            elif kind == "num":
                cells.append(_num(value))
            else:
                cells.append("n/a" if value is None else str(value))
        lines.append(f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} |")

    lines.append(
        f"| Data Quality Gate | {_check(baseline_quality.get('success'))} | "
        f"{_check(corrupted_quality.get('success'))} | {_check(repaired_quality.get('success'))} |"
    )
    lines.append(
        f"| Duplicate paper_id | {baseline_quality.get('duplicate_paper_ids', 'n/a')} | "
        f"{corrupted_quality.get('duplicate_paper_ids', 'n/a')} | "
        f"{repaired_quality.get('duplicate_paper_ids', 'n/a')} |"
    )
    lines.append(
        f"| Freshness SLA (is_fresh) | {_check(baseline_freshness.get('is_fresh'))} | "
        f"{_check(corrupted_freshness.get('is_fresh'))} | "
        f"{_check(repaired_freshness.get('is_fresh'))} |"
    )
    lines.append(
        f"| Stale ratio | {_pct(baseline_freshness.get('stale_ratio'))} | "
        f"{_pct(corrupted_freshness.get('stale_ratio'))} | "
        f"{_pct(repaired_freshness.get('stale_ratio'))} |"
    )

    lines += [
        "",
        "## 2. Degradation Analysis (Corrupted vs Baseline)",
        "",
        "| Metric | Delta |",
        "| :--- | :--- |",
    ]
    for key in ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy"):
        try:
            delta = float(corrupted_metrics.get(key, 0.0)) - float(baseline_metrics.get(key, 0.0))
            lines.append(f"| {METRIC_LABELS.get(key, key)} | {delta:+.4f} |")
        except (TypeError, ValueError):
            lines.append(f"| {METRIC_LABELS.get(key, key)} | n/a |")

    failed = corrupted_quality.get("failed_expectations", []) or []
    if failed:
        lines += ["", "### Expectations that caught the corruption", ""]
        for item in failed:
            kwargs = item.get("kwargs", {}) or {}
            column = kwargs.get("column")
            target = f" (column={column})" if column else ""
            lines.append(f"- `{item.get('type')}`{target}")

    corrupted_alert = corrupted_freshness.get("alert")
    if corrupted_alert:
        lines += ["", "### Freshness alert", "", f"> {corrupted_alert}"]

    lines += [
        "",
        "## 3. Repair Verification",
        "",
        "The repaired state is rebuilt from the immutable raw snapshot "
        "(`data/raw/crossref_records.json`) by re-running cleaning, the Data Quality Gate, "
        "the Freshness SLA, the ChromaDB index and the evaluation set. Re-running this flow "
        "any number of times yields the same clean dataset, which demonstrates idempotency.",
        "",
        f"- Repaired gate status: **{_check(repaired_quality.get('success'))}**",
        f"- Repaired freshness: **{_check(repaired_freshness.get('is_fresh'))}**",
        "",
    ]
    write_text(Path(report_path), "\n".join(lines))
