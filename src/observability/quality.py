from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json

TITLE_MIN_LENGTH = 8
TITLE_MAX_LENGTH = 300
SUMMARY_MIN_LENGTH = 1
SUMMARY_MAX_LENGTH = 4000
STALE_RATIO_LIMIT = 0.25
ROW_COUNT_TOLERANCE = 1


def _gx_resource_name(report_name: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", report_name).strip("_").lower()
    return cleaned or "papers"


def _row_count_bounds(settings: Settings) -> tuple[int, int]:
    """Expected row-count window for the gate.

    The pipeline is fail-closed: it expects the configured number of ingested
    records (minus a one-row tolerance) and rejects a batch that lost or gained
    documents before it can reach ChromaDB.
    """
    expected = max(1, int(settings.max_results))
    return max(1, expected - ROW_COUNT_TOLERANCE), max(expected + 1, expected * 3)


def _quality_report_path(settings: Settings, report_name: str) -> Path:
    mapping = {
        "baseline": settings.paths.baseline_quality_report,
        "corrupted": settings.paths.corrupted_quality_report,
        "repaired": settings.paths.quality_dir / "repaired_quality_report.json",
    }
    return mapping.get(report_name, settings.paths.quality_dir / f"{report_name}_quality_report.json")


@contextmanager
def _quiet_stderr():
    """Silence GX's raw tqdm progress bars (written to fd 2) during validation.

    GX passes ``disable`` explicitly to tqdm, so the ``TQDM_DISABLE`` environment
    variable is ignored. GX warnings and errors travel through ``logging`` on
    stderr's Python-level stream, so they are re-emitted on stdout instead of
    being lost.
    """
    try:
        saved = os.dup(2)
    except OSError:
        yield
        return

    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        sys.stderr.flush()
        os.dup2(devnull, 2)
        yield
    finally:
        try:
            sys.stderr.flush()
        except ValueError:
            pass
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)


def _camel_case(name: str) -> str:
    """``expect_column_values_to_be_null`` -> ``ExpectColumnValuesToBeNull``."""
    return "".join(part.capitalize() for part in str(name).split("_") if part)


def _extract_gx_expectations(result: Any) -> list[dict[str, Any]]:
    """Flatten a GX 1.x validation result into one entry per expectation."""
    payload = result.to_json_dict()
    raw_results = payload.get("results", []) or []
    expectations: list[dict[str, Any]] = []
    for suite_result in raw_results:
        entries = suite_result.get("expectation_results")
        if not isinstance(entries, list):
            entries = [suite_result]
        for item in entries:
            config = item.get("expectation_config", {}) or {}
            result_block = item.get("result", {}) or {}
            exception_info = item.get("exception_info", {}) or {}
            observed = result_block.get("observed_value")
            if observed is None and "element_count" in result_block:
                observed = result_block.get("element_count")
            expectations.append(
                {
                    "type": _camel_case(config.get("type", "unknown")),
                    "gx_type": config.get("type"),
                    "kwargs": {
                        key: value
                        for key, value in (config.get("kwargs", {}) or {}).items()
                        if key != "batch_id"
                    },
                    "success": bool(item.get("success")),
                    "element_count": result_block.get("element_count"),
                    "unexpected_count": result_block.get("unexpected_count"),
                    "unexpected_percent": result_block.get("unexpected_percent"),
                    "observed_value": observed,
                    "exception_message": exception_info.get("exception_message"),
                }
            )
    return expectations


def _run_gx_validation(
    df: pd.DataFrame, settings: Settings, report_name: str
) -> tuple[bool, list[dict[str, Any]], str]:
    """Run the Great Expectations 1.x ephemeral Pandas validation."""
    # GX drives tqdm internally; keep the lab console readable.
    os.environ.setdefault("TQDM_DISABLE", "1")

    import great_expectations as gx
    import great_expectations.expectations as gxe

    resource = _gx_resource_name(report_name)
    min_rows, max_rows = _row_count_bounds(settings)

    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name=f"papers_source_{resource}")
    data_asset = data_source.add_dataframe_asset(name=f"papers_asset_{resource}")
    batch_definition = data_asset.add_batch_definition_whole_dataframe(f"papers_batch_{resource}")
    dataframe = df.reset_index(drop=True)
    # Materialise the batch so the dataframe binding itself is exercised.
    batch_definition.get_batch(batch_parameters={"dataframe": dataframe})

    suite = context.suites.add(gx.ExpectationSuite(name=f"papers_suite_{resource}"))
    suite.add_expectation(
        gxe.ExpectTableRowCountToBeBetween(min_value=min_rows, max_value=max_rows)
    )
    suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="paper_id"))
    suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="title"))
    suite.add_expectation(gxe.ExpectColumnValuesToBeUnique(column="paper_id"))
    suite.add_expectation(
        gxe.ExpectColumnValueLengthsToBeBetween(
            column="title", min_value=TITLE_MIN_LENGTH, max_value=TITLE_MAX_LENGTH
        )
    )
    suite.add_expectation(
        gxe.ExpectColumnValueLengthsToBeBetween(
            column="summary", min_value=SUMMARY_MIN_LENGTH, max_value=SUMMARY_MAX_LENGTH
        )
    )

    validation_definition = gx.ValidationDefinition(
        name=f"papers_validation_{resource}",
        data=batch_definition,
        suite=suite,
    )
    with _quiet_stderr():
        result = validation_definition.run(
            batch_parameters={"dataframe": dataframe},
            result_format={"result_format": "COMPLETE"},
        )
    expectations = _extract_gx_expectations(result)
    return bool(result.success), expectations, gx.__version__


def _run_pandas_fallback(
    df: pd.DataFrame, settings: Settings
) -> tuple[bool, list[dict[str, Any]]]:
    """Mirror the GX suite in pandas so the gate still blocks bad data.

    This is only reached if the GX runtime itself is unavailable; the report
    records ``engine = pandas_fallback`` so the deviation stays visible.
    """
    min_rows, max_rows = _row_count_bounds(settings)
    row_count = int(len(df))
    paper_id = df.get("paper_id")
    title = df.get("title")
    summary = df.get("summary")

    def _not_null(series: pd.Series | None) -> tuple[bool, int]:
        if series is None:
            return False, row_count
        null_count = int(series.isna().sum() + (series.astype(str).str.strip() == "").sum())
        return null_count == 0, null_count

    def _lengths(series: pd.Series | None, min_length: int, max_length: int) -> tuple[bool, int]:
        if series is None:
            return False, row_count
        lengths = series.fillna("").astype(str).str.len()
        violations = int(((lengths < min_length) | (lengths > max_length)).sum())
        return violations == 0, violations

    paper_id_ok, paper_id_nulls = _not_null(paper_id)
    title_ok, title_nulls = _not_null(title)
    unique_ok = bool(paper_id is not None and not paper_id.duplicated().any())
    duplicate_count = int(paper_id.duplicated().sum()) if paper_id is not None else row_count
    title_len_ok, title_len_violations = _lengths(title, TITLE_MIN_LENGTH, TITLE_MAX_LENGTH)
    summary_len_ok, summary_len_violations = _lengths(summary, SUMMARY_MIN_LENGTH, SUMMARY_MAX_LENGTH)

    expectations = [
        {
            "type": "ExpectTableRowCountToBeBetween",
            "kwargs": {"min_value": min_rows, "max_value": max_rows},
            "success": min_rows <= row_count <= max_rows,
            "observed_value": row_count,
        },
        {
            "type": "ExpectColumnValuesToNotBeNull",
            "kwargs": {"column": "paper_id"},
            "success": paper_id_ok,
            "unexpected_count": paper_id_nulls,
        },
        {
            "type": "ExpectColumnValuesToNotBeNull",
            "kwargs": {"column": "title"},
            "success": title_ok,
            "unexpected_count": title_nulls,
        },
        {
            "type": "ExpectColumnValuesToBeUnique",
            "kwargs": {"column": "paper_id"},
            "success": unique_ok,
            "unexpected_count": duplicate_count,
        },
        {
            "type": "ExpectColumnValueLengthsToBeBetween",
            "kwargs": {"column": "title", "min_value": TITLE_MIN_LENGTH, "max_value": TITLE_MAX_LENGTH},
            "success": title_len_ok,
            "unexpected_count": title_len_violations,
        },
        {
            "type": "ExpectColumnValueLengthsToBeBetween",
            "kwargs": {
                "column": "summary",
                "min_value": SUMMARY_MIN_LENGTH,
                "max_value": SUMMARY_MAX_LENGTH,
            },
            "success": summary_len_ok,
            "unexpected_count": summary_len_violations,
        },
    ]
    return all(item["success"] for item in expectations), expectations


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run the Great Expectations 1.x Data Quality Gate and persist the report.

    Checks row count, ``paper_id``/``title`` nullability, ``paper_id`` uniqueness
    and title/summary length bounds, then writes a JSON report under
    ``data/quality/``. The returned ``success`` flag is what the pipeline uses to
    block indexing (fail-closed).
    """
    if df is None:
        raise ValueError("run_data_quality_checks requires a dataframe.")

    gx_error: str | None = None
    gx_version: str | None = None
    try:
        success, expectations, gx_version = _run_gx_validation(df, settings, report_name)
        engine = "great_expectations"
    except Exception as exc:  # noqa: BLE001 - keep the gate fail-closed, never fail-open
        gx_error = f"{type(exc).__name__}: {exc}"
        success, expectations = _run_pandas_fallback(df, settings)
        engine = "pandas_fallback"

    min_rows, max_rows = _row_count_bounds(settings)
    failed = [item for item in expectations if not item["success"]]
    report: dict[str, Any] = {
        "report_name": report_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "gx_version": gx_version if engine == "great_expectations" else None,
        "success": bool(success),
        "status": "pass" if success else "fail",
        "row_count": int(len(df)),
        "row_count_expectation": {"min_value": min_rows, "max_value": max_rows},
        "duplicate_paper_ids": int(df["paper_id"].duplicated().sum()) if "paper_id" in df else 0,
        "expectation_count": len(expectations),
        "failed_expectation_count": len(failed),
        "failed_expectations": [
            {"type": item["type"], "kwargs": item["kwargs"], "observed_value": item.get("observed_value")}
            for item in failed
        ],
        "expectations": expectations,
    }
    if gx_error:
        report["gx_error"] = gx_error

    report_path = _quality_report_path(settings, report_name)
    write_json(report_path, report)

    try:
        gx_dir = settings.paths.gx_dir
        gx_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            gx_dir / f"{_gx_resource_name(report_name)}_validation.json",
            {
                "report_name": report_name,
                "engine": engine,
                "success": bool(success),
                "expectations": expectations,
            },
        )
    except OSError:
        pass

    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path: Path) -> dict[str, Any]:
    """Summarise corpus freshness and enforce the Freshness SLA.

    A batch is considered stale when more than ``STALE_RATIO_LIMIT`` (25%) of its
    rows exceed ``settings.freshness_threshold_days`` days of age.
    """
    threshold_days = int(settings.freshness_threshold_days)
    total_rows = int(len(df))

    if total_rows == 0:
        report: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "threshold_days": threshold_days,
            "stale_ratio_limit": STALE_RATIO_LIMIT,
            "total_rows": 0,
            "stale_rows": 0,
            "stale_ratio": 1.0,
            "is_fresh": False,
            "status": "alert",
            "alert": "Empty batch: no documents available to serve.",
            "latest_published": None,
            "oldest_published": None,
            "max_age_days": None,
            "mean_age_days": None,
            "median_age_days": None,
        }
        write_json(Path(report_path), report)
        return report

    if "age_days" in df.columns:
        ages = pd.to_numeric(df["age_days"], errors="coerce")
    else:
        published = pd.to_datetime(df.get("published"), errors="coerce")
        ages = (pd.Timestamp.now(tz="UTC").normalize() - published).dt.days
    ages = ages.dropna()

    published_dates = pd.to_datetime(df.get("published"), errors="coerce")
    stale_mask = ages > threshold_days
    stale_rows = int(stale_mask.sum())
    stale_ratio = round(stale_rows / total_rows, 4) if total_rows else 0.0
    is_fresh = stale_ratio <= STALE_RATIO_LIMIT

    alert = None
    if not is_fresh:
        alert = (
            f"Freshness SLA breached: {stale_ratio:.1%} of rows are older than "
            f"{threshold_days} days (limit {STALE_RATIO_LIMIT:.0%})."
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_days": threshold_days,
        "stale_ratio_limit": STALE_RATIO_LIMIT,
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "stale_ratio": stale_ratio,
        "is_fresh": bool(is_fresh),
        "status": "ok" if is_fresh else "alert",
        "alert": alert,
        "latest_published": None if published_dates.dropna().empty else published_dates.max().date().isoformat(),
        "oldest_published": None if published_dates.dropna().empty else published_dates.min().date().isoformat(),
        "max_age_days": None if ages.empty else int(ages.max()),
        "mean_age_days": None if ages.empty else round(float(ages.mean()), 2),
        "median_age_days": None if ages.empty else round(float(ages.median()), 2),
    }
    write_json(Path(report_path), report)
    return report
