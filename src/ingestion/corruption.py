from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import write_json


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Apply six deterministic data-corruption scenarios to a clean dataframe."""
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")
    required = {"paper_id", "title", "summary", "published", "authors_joined", "categories_joined"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Clean dataframe is missing required columns: {sorted(missing)}")

    corrupted = df.copy(deep=True).reset_index(drop=True)
    log: list[dict[str, Any]] = []

    def record(scenario: str, indices: list[int], action: str) -> None:
        log.append(
            {
                "scenario": scenario,
                "action": action,
                "rows_affected": len(indices),
                "paper_ids": [str(value) for value in corrupted.loc[indices, "paper_id"].tolist()],
            }
        )

    # Remove the newest fifth of the corpus to simulate a freshness outage.
    newest_count = max(1, len(corrupted) // 5)
    newest_indices = corrupted.sort_values("published", ascending=False).index[:newest_count].tolist()
    corrupted = corrupted.drop(index=newest_indices).reset_index(drop=True)
    log.append(
        {
            "scenario": "drop_latest_records",
            "action": "Dropped the newest records before downstream indexing.",
            "rows_affected": len(newest_indices),
            "paper_ids": [str(value) for value in df.loc[newest_indices, "paper_id"].tolist()],
        }
    )

    blank_indices = list(corrupted.index[: max(1, len(corrupted) // 10)])
    corrupted.loc[blank_indices, "summary"] = ""
    record("blank_summary", blank_indices, "Blanked summary values.")

    noise_indices = list(corrupted.index[:: max(1, len(corrupted) // 4)][:3])
    corrupted.loc[noise_indices, "text_for_embedding"] = corrupted.loc[noise_indices, "text_for_embedding"].astype(str) + " ### $$$ ??? NOISE_0xDEADBEEF"
    record("inject_text_noise", noise_indices, "Appended non-semantic noise to embedding text.")

    title_indices = list(corrupted.index[1: 1 + max(1, len(corrupted) // 10)])
    corrupted.loc[title_indices, "title"] = corrupted.loc[title_indices, "title"].astype(str).str.slice(0, 9)
    record("truncate_title", title_indices, "Truncated titles below ten characters.")

    stale_indices = list(corrupted.index[-max(1, len(corrupted) // 10):])
    stale_date = (datetime.now(UTC).date() - timedelta(days=5 * 365)).isoformat()
    corrupted.loc[stale_indices, "published"] = stale_date
    corrupted.loc[stale_indices, "age_days"] = 5 * 365
    record("stale_date", stale_indices, f"Set published date to {stale_date}.")

    duplicate_count = min(newest_count, len(corrupted))
    duplicate_indices = list(corrupted.index[:duplicate_count])
    corrupted = pd.concat([corrupted, corrupted.loc[duplicate_indices]], ignore_index=True)
    log.append(
        {
            "scenario": "duplicate_rows",
            "action": "Appended duplicate copies of existing records.",
            "rows_affected": duplicate_count,
            "paper_ids": [str(value) for value in corrupted.loc[len(corrupted) - duplicate_count :, "paper_id"].tolist()],
        }
    )

    corrupted["summary_chars"] = corrupted["summary"].astype(str).str.len()
    corrupted["text_for_embedding"] = corrupted.apply(
        lambda row: "\n".join(
            [
                f"Title: {row['title']}",
                f"Authors: {row['authors_joined']}",
                f"Published: {row['published']}",
                f"Categories: {row['categories_joined']}",
                f"Summary: {row['summary']}",
            ]
        ),
        axis=1,
    )
    # Preserve the injected noise after rebuilding the canonical text.
    noise_ids = set(corrupted.loc[noise_indices, "paper_id"].astype(str))
    noise_mask = corrupted["paper_id"].astype(str).isin(noise_ids)
    corrupted.loc[noise_mask, "text_for_embedding"] += " ### $$$ ??? NOISE_0xDEADBEEF"
    path = Path(output_log_path)
    write_json(path, {"total_scenarios": 6, "original_rows": len(df), "corrupted_rows": len(corrupted), "scenarios": log})
    return corrupted.reset_index(drop=True)
