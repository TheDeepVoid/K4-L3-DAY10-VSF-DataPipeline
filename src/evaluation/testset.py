from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json
from ingestion.cleaning import sort_newest_first

QUESTION_TYPES = ("summary", "authors", "date", "categories")
TEST_SET_SIZE = 10
MIN_DOCUMENTS = len(QUESTION_TYPES)


def _ground_truth(question_type: str, title: str, row: dict[str, Any]) -> tuple[str, str]:
    """Return (question, ground_truth) aligned with ``retrieval.qa._extract_answer``.

    The benchmark deliberately targets the newest publications: they are the
    rows the corruption suite targets, and they are exactly the records a
    stale/incomplete ingestion would silently drop in production.
    """
    if question_type == "authors":
        return f"Who authored '{title}'?", str(row.get("authors_joined", "")).strip()
    if question_type == "date":
        return f"When was '{title}' published?", str(row.get("published", "")).strip()
    if question_type == "categories":
        return f"What categories does '{title}' belong to?", str(row.get("categories_joined", "")).strip()
    summary = str(row.get("summary", "")).strip()
    return (
        f"What is the main contribution described in '{title}'?",
        first_sentence(summary),
    )


def build_test_set(df: pd.DataFrame, output_path: Path) -> list[dict[str, Any]]:
    """Create the evaluation set from a cleaned dataframe.

    Produces ``TEST_SET_SIZE`` questions spread across the four business groups
    (``summary``, ``authors``, ``date``, ``categories``) and persists them to
    ``output_path``. Selection is deterministic so baseline, corrupted and
    repaired runs are scored against exactly the same questions.
    """
    if df is None or df.empty:
        raise ValueError("Cannot build a test set from an empty dataframe.")
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(
            f"Need at least {MIN_DOCUMENTS} documents to cover all question types, got {len(df)}."
        )

    selected = sort_newest_first(df).head(TEST_SET_SIZE)
    records = selected.to_dict(orient="records")

    items: list[dict[str, Any]] = []
    for position, row in enumerate(records):
        question_type = QUESTION_TYPES[position % len(QUESTION_TYPES)]
        title = str(row.get("title", "")).strip()
        paper_id = str(row.get("paper_id", "")).strip()
        if not title or not paper_id:
            continue
        question, ground_truth = _ground_truth(question_type, title, row)
        items.append(
            {
                "id": f"q{len(items) + 1:02d}-{question_type}",
                "question_type": question_type,
                "question": question,
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [paper_id],
                "paper_id": paper_id,
                "paper_title": title,
            }
        )

    if not items:
        raise ValueError("No usable documents found while building the test set.")

    write_json(Path(output_path), items)
    return items
