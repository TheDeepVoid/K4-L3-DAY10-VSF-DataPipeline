from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from core.config import Settings, load_settings, require_llm_credentials
from core.utils import ensure_parent, now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex

logger = logging.getLogger(__name__)

DEMO_QUESTION_COUNT = 3


def load_source_records(settings: Settings) -> list:
    """Load records from the raw snapshot, or refresh them when explicitly asked."""
    if settings.refresh_source:
        return fetch_source_records(settings)
    if settings.paths.raw_records_json.exists():
        return load_raw_records(settings.paths.raw_records_json)
    if settings.paths.raw_api_response.exists():
        return load_raw_records(settings.paths.raw_api_response)
    return fetch_source_records(settings)


def save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    ensure_parent(csv_path)
    write_csv(df, csv_path)
    ensure_parent(json_path)
    df.to_json(json_path, orient="records", indent=2)


def resolve_test_set(df: pd.DataFrame, settings: Settings) -> list[dict[str, Any]]:
    """Reuse the benchmark when it still matches the corpus, otherwise rebuild it.

    The corrupted and repaired runs must be scored against exactly the same
    questions as the baseline, so caching is only honoured when every referenced
    document is still present.
    """
    testset_path = settings.paths.eval_testset
    if testset_path.exists() and not settings.refresh_test_set:
        try:
            cached = read_json(testset_path)
        except (ValueError, OSError):
            cached = None
        if isinstance(cached, list) and cached:
            known_ids = set(df["paper_id"].astype(str))
            referenced = {
                str(doc_id)
                for item in cached
                for doc_id in (item.get("ground_truth_doc_ids") or [])
            }
            if referenced and referenced.issubset(known_ids):
                logger.info("Reusing cached evaluation set (%s questions).", len(cached))
                return cached
    return build_test_set(df, testset_path)


def run_agent_demo(settings: Settings, index: LocalEmbeddingIndex, test_set: list[dict[str, Any]]) -> None:
    """Best-effort agent demo; skipped when no LLM credentials are configured."""
    try:
        require_llm_credentials(settings)
    except RuntimeError as exc:
        print(f"[CP3] Agent demo skipped: {exc}")
        return

    questions = [str(item["question"]) for item in test_set[:DEMO_QUESTION_COUNT]]
    try:
        agent = build_agent(settings, index)
        answers = [
            {"question": question, "answer": run_agent_question(agent, question)}
            for question in questions
        ]
    except Exception as exc:  # noqa: BLE001 - the demo must never fail the pipeline
        logger.warning("Agent demo unavailable: %s", exc)
        print(f"[CP3] Agent demo skipped: {exc}")
        return

    write_json(settings.paths.demo_answers, answers)
    print(f"[CP3] Agent demo answered {len(answers)} sample question(s) -> {settings.paths.demo_answers}")


def main() -> None:
    """Run the baseline pipeline end-to-end (CP0 -> CP3)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings()
    run_date = now_utc()
    paths = settings.paths

    print("=" * 72)
    print("PHASE 1 - BASELINE PIPELINE (CP0 -> CP3)")
    print("=" * 72)

    # CP0 - raw ingestion (offline snapshot by default).
    records = load_source_records(settings)
    print(f"Tín hiệu hoàn thành: Đã tải {len(records)} bài báo")
    if not records:
        raise RuntimeError("Raw ingestion produced no records; aborting baseline pipeline.")

    # CP1 - cleaning + quality gate.
    df = build_clean_dataframe(records, run_date)
    if df.empty:
        raise RuntimeError("Cleaning produced an empty dataframe; aborting baseline pipeline.")
    print(f"Tín hiệu hoàn thành: Clean thành công {len(df)} dòng")
    save_dataframe(df, paths.clean_csv, paths.clean_json)

    quality = run_data_quality_checks(df, settings, "baseline")
    print(f"Tín hiệu hoàn thành: Quality check status = {quality['success']}")
    if quality.get("gx_error"):
        print(f"[CP1] WARNING: Great Expectations runtime error, used pandas fallback: {quality['gx_error']}")

    freshness = build_freshness_report(df, settings, paths.freshness_report)
    print(f"Tín hiệu hoàn thành: Freshness is_fresh = {freshness['is_fresh']}")
    if freshness.get("alert"):
        print(f"[CP1] ALERT: {freshness['alert']}")

    # Fail closed: bad data must never reach the vector store.
    allow_stale = os.getenv("ALLOW_STALE_DATA", "").lower() in {"1", "true", "yes"}
    if not quality["success"]:
        failed = ", ".join(item["type"] for item in quality.get("failed_expectations", []))
        raise RuntimeError(f"Data Quality Gate blocked indexing. Failed expectations: {failed}")
    if not freshness["is_fresh"] and not allow_stale:
        raise RuntimeError(
            f"Freshness SLA blocked indexing: {freshness['alert']}. "
            "Set ALLOW_STALE_DATA=1 to override for a live demo."
        )

    # CP2 - vector index + benchmark.
    index = LocalEmbeddingIndex.build(df, settings, paths.embeddings_json)
    print(f"[CP2] ChromaDB collection '{index.collection_name}' indexed {len(df)} documents")

    test_set = resolve_test_set(df, settings)
    print(f"[CP2] Evaluation set ready with {len(test_set)} questions -> {paths.eval_testset}")

    # CP3 - benchmark + report.
    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=paths.eval_testset,
        metrics_output_path=paths.baseline_metrics,
        answers_output_path=paths.baseline_answers,
    )
    print(
        "[CP3] Baseline metrics: "
        f"hit_rate={bundle.summary['retrieval_hit_rate']:.4f} "
        f"token_f1={bundle.summary['mean_token_f1']:.4f} "
        f"judge_accuracy={bundle.summary['judge_accuracy']:.4f}"
    )

    source_summary = {
        "Source": settings.source_api,
        "Mode": "live API" if settings.refresh_source else "offline snapshot",
        "Query": settings.source_query,
        "Max results requested": settings.max_results,
        "Records parsed": len(records),
        "Clean rows": len(df),
        "Embedding model": settings.embedding_model,
        "Chroma collection": index.collection_name,
        "Raw response": str(paths.raw_api_response),
        "Raw records": str(paths.raw_records_json),
    }
    generate_phase1_report(
        report_path=paths.baseline_report,
        source_summary=source_summary,
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )
    print(f"[CP3] Phase 1 report -> {paths.baseline_report}")

    run_agent_demo(settings, index, test_set)

    print("-" * 72)
    print("PHASE 1 COMPLETE")
    print(f"  clean data     : {paths.clean_csv}")
    print(f"  test set       : {paths.eval_testset}")
    print(f"  metrics        : {paths.baseline_metrics}")
    print(f"  report         : {paths.baseline_report}")
    print("-" * 72)


if __name__ == "__main__":  # pragma: no cover
    main()
