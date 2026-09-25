from __future__ import annotations

from typing import Any
import json
from pathlib import Path

import great_expectations as gx
import pandas as pd
from great_expectations.expectations import (
    ExpectColumnValueLengthsToBeBetween,
    ExpectColumnValuesToBeUnique,
    ExpectColumnValuesToNotBeNull,
    ExpectTableRowCountToBeBetween,
)

from core.config import Settings


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run the GX 1.x quality gate and persist a compact JSON report."""
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})
    suite = gx.ExpectationSuite(name=f"papers_quality_{report_name}")
    expectations = [
        ExpectTableRowCountToBeBetween(min_value=5, max_value=5000),
        ExpectColumnValuesToNotBeNull(column="paper_id"),
        ExpectColumnValuesToNotBeNull(column="title"),
        ExpectColumnValuesToNotBeNull(column="text_for_embedding"),
        ExpectColumnValuesToBeUnique(column="paper_id"),
        ExpectColumnValueLengthsToBeBetween(column="summary", min_value=30),
    ]
    for expectation in expectations:
        suite.add_expectation(expectation)
    context.suites.add(suite)
    validation_definition = gx.ValidationDefinition(
        name=f"{report_name}_validation",
        data=batch_def,
        suite=suite,
    )
    context.validation_definitions.add(validation_definition)
    validation_result = validation_definition.run(batch_parameters={"dataframe": df})
    stale_rows = int((pd.to_numeric(df.get("age_days", pd.Series(dtype=float)), errors="coerce") > settings.freshness_threshold_days).sum())
    total_rows = len(df)
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    freshness = {
        "latest_published": str(pd.to_datetime(df["published"], errors="coerce").max().date()) if total_rows else None,
        "oldest_published": str(pd.to_datetime(df["published"], errors="coerce").min().date()) if total_rows else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": stale_ratio,
        "threshold_days": settings.freshness_threshold_days,
        "max_stale_ratio": 0.25,
        "is_fresh": stale_ratio <= 0.25,
    }
    result = {
        "success": bool(validation_result.success),
        "freshness": freshness,
        "expectations": [
            {"type": item.expectation_config.type, "success": bool(item.success)}
            for item in validation_result.results
        ],
    }
    settings.paths.quality_dir.mkdir(parents=True, exist_ok=True)
    (settings.paths.quality_dir / f"{report_name}_quality_report.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Write the freshness summary used by monitoring and reports."""
    total_rows = len(df)
    stale_rows = int((pd.to_numeric(df.get("age_days", pd.Series(dtype=float)), errors="coerce") > settings.freshness_threshold_days).sum())
    published = pd.to_datetime(df.get("published", pd.Series(dtype=str)), errors="coerce")
    payload = {
        "latest_published": str(published.max().date()) if total_rows else None,
        "oldest_published": str(published.min().date()) if total_rows else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": stale_rows / total_rows <= 0.25 if total_rows else False,
    }
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
