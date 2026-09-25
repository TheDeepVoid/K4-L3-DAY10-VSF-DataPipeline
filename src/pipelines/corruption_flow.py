from __future__ import annotations

import logging

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import load_source_records, main as run_phase1, save_dataframe
from retrieval.index import LocalEmbeddingIndex

logger = logging.getLogger(__name__)

# age_days depends on wall-clock time, so it is excluded when proving that the
# repair reproduces the baseline byte-for-byte.
IDEMPOTENCY_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "summary_chars",
    "text_for_embedding",
]


def _print_comparison(baseline: dict, corrupted: dict, repaired: dict, quality: dict, freshness: dict) -> None:
    rows = [
        ("Retrieval Hit Rate", "retrieval_hit_rate", "pct"),
        ("Mean Token F1", "mean_token_f1", "num"),
        ("Judge Accuracy", "judge_accuracy", "pct"),
        ("Mean Judge Score", "mean_judge_score", "num"),
    ]
    header = f"{'Metric':<22}{'Baseline':>12}{'Corrupted':>12}{'Repaired':>12}"
    print("\n" + "=" * 72)
    print("BASELINE vs CORRUPTED vs REPAIRED")
    print("=" * 72)
    print(header)
    print("-" * 72)
    for label, key, kind in rows:
        cells = []
        for metrics in (baseline, corrupted, repaired):
            value = metrics.get(key)
            if value is None:
                cells.append("n/a")
            elif kind == "pct":
                cells.append(f"{float(value) * 100:.1f}%")
            else:
                cells.append(f"{float(value):.4f}")
        print(f"{label:<22}{cells[0]:>12}{cells[1]:>12}{cells[2]:>12}")
    print("-" * 72)
    print(f"{'Quality Gate':<22}{'PASS':>12}{'FAIL' if not quality.get('success') else 'PASS':>12}{'PASS':>12}")
    print(
        f"{'Freshness SLA':<22}{'ok':>12}"
        f"{'alert' if not freshness.get('corrupted_is_fresh') else 'ok':>12}"
        f"{'alert' if not freshness.get('repaired_is_fresh') else 'ok':>12}"
    )
    print("=" * 72)


def main() -> None:
    """Run corruption -> evaluate -> repair -> compare (CP4 -> CP5)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings()
    paths = settings.paths

    print("=" * 72)
    print("PHASE 2 - CORRUPTION, REPAIR & COMPARISON (CP4 -> CP5)")
    print("=" * 72)

    # Ensure a baseline exists; build it on demand so the flow is self-contained.
    if not paths.baseline_metrics.exists() or not paths.clean_csv.exists():
        print("[CP4] Baseline artifacts missing - running Phase 1 first.")
        run_phase1()

    baseline_metrics = read_json(paths.baseline_metrics)
    baseline_df = pd.read_csv(paths.clean_csv, keep_default_na=False, dtype=str)
    baseline_df["age_days"] = pd.to_numeric(baseline_df["age_days"], errors="coerce").fillna(0).astype(int)
    baseline_df["summary_chars"] = pd.to_numeric(baseline_df["summary_chars"], errors="coerce").fillna(0).astype(int)
    print(f"[CP4] Loaded baseline: {len(baseline_df)} rows")

    # CP4 - inject the six corruptions and persist the damaged artifacts.
    corrupted_df = corrupt_clean_dataframe(baseline_df, paths.corruption_log)
    save_dataframe(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)
    print(f"[CP4] Corrupted dataset: {len(baseline_df)} -> {len(corrupted_df)} rows")
    print(f"[CP4] Corruption log -> {paths.corruption_log}")

    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.corrupted_freshness_report
    )
    print(f"[CP4] Corrupted Quality Gate success = {corrupted_quality['success']} (expected False)")
    print(
        f"[CP4] Corrupted Freshness is_fresh = {corrupted_freshness['is_fresh']} "
        f"(stale {corrupted_freshness['stale_ratio']:.1%})"
    )
    if corrupted_quality.get("gx_error"):
        print(f"[CP4] WARNING: GX runtime error, used pandas fallback: {corrupted_quality['gx_error']}")

    # The corrupted index is built deliberately: the lab must demonstrate the
    # silent failure that the gate is designed to prevent.
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df, settings, paths.corrupted_embeddings_json
    )
    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.corrupted_metrics,
        answers_output_path=paths.corrupted_answers,
    )
    print(
        "[CP4] Corrupted metrics: "
        f"hit_rate={corrupted_bundle.summary['retrieval_hit_rate']:.4f} "
        f"token_f1={corrupted_bundle.summary['mean_token_f1']:.4f}"
    )

    # CP5 - idempotent repair from the immutable raw snapshot.
    records = load_source_records(settings)
    repaired_df = build_clean_dataframe(records, now_utc())
    if repaired_df.empty:
        raise RuntimeError("Repair produced an empty dataframe; cannot continue.")
    save_dataframe(repaired_df, paths.repaired_clean_csv, paths.repaired_clean_json)
    print(f"[CP5] Repaired dataset rebuilt from raw: {len(repaired_df)} rows")

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.repaired_freshness_report
    )
    print(f"[CP5] Repaired Quality Gate success = {repaired_quality['success']} (expected True)")
    print(f"[CP5] Repaired Freshness is_fresh = {repaired_freshness['is_fresh']}")

    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.repaired_metrics,
        answers_output_path=paths.repaired_answers,
    )
    print(
        "[CP5] Repaired metrics: "
        f"hit_rate={repaired_bundle.summary['retrieval_hit_rate']:.4f} "
        f"token_f1={repaired_bundle.summary['mean_token_f1']:.4f}"
    )

    comparable = [column for column in IDEMPOTENCY_COLUMNS if column in baseline_df.columns]
    repaired_sorted = repaired_df.sort_values("paper_id").reset_index(drop=True)
    baseline_sorted = baseline_df.sort_values("paper_id").reset_index(drop=True)
    identical = (
        len(repaired_sorted) == len(baseline_sorted)
        and repaired_sorted[comparable].equals(baseline_sorted[comparable])
    )
    print(f"[CP5] Idempotent repair verified against baseline: {identical}")

    if not repaired_quality["success"]:
        raise RuntimeError("Repair failed the Data Quality Gate; manual intervention required.")

    baseline_freshness = (
        read_json(paths.freshness_report) if paths.freshness_report.exists() else {}
    )
    _print_comparison(
        baseline_metrics,
        corrupted_bundle.summary,
        repaired_bundle.summary,
        corrupted_quality,
        {
            "corrupted_is_fresh": corrupted_freshness["is_fresh"],
            "repaired_is_fresh": repaired_freshness["is_fresh"],
        },
    )

    generate_corruption_report(
        report_path=paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(f"\n[CP5] Comparison report -> {paths.comparison_report}")
    print(f"[CP5] Baseline freshness was_fresh = {baseline_freshness.get('is_fresh', 'n/a')}")

    print("-" * 72)
    print("PHASE 2 COMPLETE")
    print(f"  corruption log     : {paths.corruption_log}")
    print(f"  corrupted metrics  : {paths.corrupted_metrics}")
    print(f"  repaired metrics   : {paths.repaired_metrics}")
    print(f"  comparison report  : {paths.comparison_report}")
    print("-" * 72)


if __name__ == "__main__":  # pragma: no cover
    main()
