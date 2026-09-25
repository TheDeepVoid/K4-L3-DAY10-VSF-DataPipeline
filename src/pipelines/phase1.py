from __future__ import annotations

from datetime import UTC, datetime

from core.config import load_settings
from core.utils import write_csv, write_json
from evaluation.testset import load_or_create_test_set
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex

def main() -> None:
    """Run ingestion, cleaning, quality, indexing, evaluation, and reporting."""
    settings = load_settings()
    records = fetch_source_records(settings)
    clean_df = build_clean_dataframe(records, datetime.now(UTC))
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, clean_df.to_dict(orient="records"))

    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    test_set = load_or_create_test_set(clean_df, settings.paths.eval_testset)

    index = LocalEmbeddingIndex(settings, collection_name=settings.baseline_collection_name)
    index.build_from_clean()
    evaluation = evaluate_pipeline(
        settings,
        index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    generate_phase1_report(
        settings.paths.baseline_report,
        {"source_api": settings.source_api, "records": len(records), "benchmark_samples": len(test_set.samples)},
        evaluation.summary,
        quality,
        freshness,
    )
    print(f"Phase 1 complete: {len(records)} records, {len(test_set.samples)} benchmark samples")
