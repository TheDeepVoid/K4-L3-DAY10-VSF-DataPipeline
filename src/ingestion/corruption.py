from __future__ import annotations

import math
from pathlib import Path
import random
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import rebuild_text_for_embedding, sort_newest_first

CORRUPTION_SEED = 42
DROP_LATEST_RATIO = 0.20
STALE_DATE_RATIO = 0.35
STALE_PUBLISHED = "1990-01-01"
BLANK_SUMMARY_ROWS = 2
NOISE_SUMMARY_ROWS = 2
TRUNCATED_TITLE_ROWS = 2
TRUNCATED_TITLE_LENGTH = 3
DUPLICATED_ROWS = 2
NOISE_ALPHABET = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~"

CORRUPTION_TYPES = (
    "drop_latest_records",
    "blank_summary",
    "inject_noise",
    "truncate_title",
    "stale_date",
    "duplicate_rows",
)


def _newest_labels(df: pd.DataFrame) -> list[int]:
    """Positional labels (0..n-1) ordered newest publication first."""
    ordered = sort_newest_first(df)
    return list(ordered.index)


def _stale_age_days(published: str) -> int:
    published_dt = pd.to_datetime(published, errors="coerce")
    if pd.isna(published_dt):
        return 0
    published_day = published_dt.date()
    return max(0, (now_utc().date() - published_day).days)


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path) -> pd.DataFrame:
    """Inject the six controlled corruption scenarios required by CP4.

    The suite is deterministic (``CORRUPTION_SEED``) and deliberately targets the
    newest publications, because those rows are both the most frequent in the
    benchmark set and the most damaging to lose. Every mutation is logged so the
    resulting Quality Gate failure and metric drop can be explained.
    """
    log_path = Path(output_log_path)
    if df is None or df.empty:
        write_json(
            log_path,
            {
                "seed": CORRUPTION_SEED,
                "original_row_count": 0,
                "corrupted_row_count": 0,
                "corruption_types": list(CORRUPTION_TYPES),
                "summary": {name: 0 for name in CORRUPTION_TYPES},
                "corruptions": [],
                "error": "Input dataframe was empty; no corruption applied.",
            },
        )
        return pd.DataFrame() if df is None else df.copy()

    rng = random.Random(CORRUPTION_SEED)
    work = df.copy().reset_index(drop=True)
    original_row_count = len(work)
    newest_first = _newest_labels(work)
    cursor = 0

    def take_newest(count: int) -> list[int]:
        """Consume up to ``count`` still-intact labels from the newest-first queue."""
        nonlocal cursor
        selected: list[int] = []
        while cursor < len(newest_first) and len(selected) < count:
            label = newest_first[cursor]
            cursor += 1
            selected.append(label)
        return selected

    corruptions: list[dict[str, Any]] = []

    # 1. Drop latest records (incomplete ingestion).
    drop_count = max(1, math.ceil(DROP_LATEST_RATIO * original_row_count))
    drop_labels = take_newest(drop_count)
    dropped_ids = [str(work.at[label, "paper_id"]) for label in drop_labels]
    corruptions.append(
        {
            "type": "drop_latest_records",
            "description": "Ingestion dropped the newest 20% of records.",
            "affected_rows": len(drop_labels),
            "paper_ids": dropped_ids,
        }
    )
    work = work.drop(index=drop_labels)

    remaining = len(work)
    if remaining == 0:
        write_json(
            log_path,
            {
                "seed": CORRUPTION_SEED,
                "original_row_count": original_row_count,
                "corrupted_row_count": 0,
                "corruption_types": list(CORRUPTION_TYPES),
                "summary": {name: 0 for name in CORRUPTION_TYPES},
                "corruptions": corruptions,
                "error": "All rows were dropped; remaining corruptions skipped.",
            },
        )
        return work.reset_index(drop=True)

    # 2. Blank summaries (cleaning failure).
    blank_labels = take_newest(BLANK_SUMMARY_ROWS)
    blank_ids: list[str] = []
    for label in blank_labels:
        blank_ids.append(str(work.at[label, "paper_id"]))
        work.at[label, "summary"] = ""
    corruptions.append(
        {
            "type": "blank_summary",
            "description": "Summary emptied for selected rows.",
            "affected_rows": len(blank_labels),
            "paper_ids": blank_ids,
        }
    )

    # 3. Inject noise characters into summaries.
    noise_labels = take_newest(NOISE_SUMMARY_ROWS)
    noise_ids: list[str] = []
    for label in noise_labels:
        noise_ids.append(str(work.at[label, "paper_id"]))
        garbage = "".join(rng.choice(NOISE_ALPHABET) for _ in range(12))
        current = str(work.at[label, "summary"])
        work.at[label, "summary"] = f"{current} {garbage}"
    corruptions.append(
        {
            "type": "inject_noise",
            "description": "Random punctuation injected into summaries.",
            "affected_rows": len(noise_labels),
            "paper_ids": noise_ids,
        }
    )

    # 4. Truncate titles below the quality minimum length.
    truncate_labels = take_newest(TRUNCATED_TITLE_ROWS)
    truncated_ids: list[str] = []
    for label in truncate_labels:
        truncated_ids.append(str(work.at[label, "paper_id"]))
        title = str(work.at[label, "title"])
        if title:
            work.at[label, "title"] = title[:TRUNCATED_TITLE_LENGTH]
    corruptions.append(
        {
            "type": "truncate_title",
            "description": f"Titles truncated to {TRUNCATED_TITLE_LENGTH} characters.",
            "affected_rows": len(truncate_labels),
            "paper_ids": truncated_ids,
        }
    )

    # 5. Stale publication dates (must breach the 25% Freshness SLA).
    stale_count = max(1, math.ceil(STALE_DATE_RATIO * remaining))
    stale_labels = take_newest(stale_count)
    stale_ids: list[str] = []
    for label in stale_labels:
        stale_ids.append(str(work.at[label, "paper_id"]))
        work.at[label, "published"] = STALE_PUBLISHED
        work.at[label, "updated"] = STALE_PUBLISHED
        work.at[label, "age_days"] = _stale_age_days(STALE_PUBLISHED)
    corruptions.append(
        {
            "type": "stale_date",
            "description": f"Publication dates rewritten to {STALE_PUBLISHED}.",
            "affected_rows": len(stale_labels),
            "paper_ids": stale_ids,
        }
    )

    # 6. Duplicate rows (index-level contamination).
    duplicate_count = max(1, min(DUPLICATED_ROWS, len(work)))
    duplicate_source = list(work.index[-duplicate_count:])
    duplicated = work.loc[duplicate_source].copy()
    duplicated["paper_id"] = duplicated["paper_id"].astype(str)  # keep ids stable for the unique check
    work = pd.concat([work, duplicated], ignore_index=True)
    corruptions.append(
        {
            "type": "duplicate_rows",
            "description": "Selected rows duplicated, creating repeated paper_id values.",
            "affected_rows": len(duplicated),
            "paper_ids": duplicated["paper_id"].astype(str).tolist(),
        }
    )

    # Rebuild the embedded representation from the damaged fields so ChromaDB
    # indexes exactly what a production pipeline would have indexed.
    work = work.reset_index(drop=True)
    work["text_for_embedding"] = work.apply(rebuild_text_for_embedding, axis=1)
    work = work.sort_values(
        ["published", "paper_id"], ascending=[False, True], kind="mergesort", na_position="last"
    ).reset_index(drop=True)

    summary_counts = {name: 0 for name in CORRUPTION_TYPES}
    for event in corruptions:
        summary_counts[event["type"]] += int(event["affected_rows"])

    write_json(
        log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": CORRUPTION_SEED,
            "original_row_count": original_row_count,
            "corrupted_row_count": len(work),
            "corruption_types": list(CORRUPTION_TYPES),
            "summary": summary_counts,
            "corruptions": corruptions,
        },
    )
    return work
