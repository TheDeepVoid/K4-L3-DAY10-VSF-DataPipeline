from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
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
    "age_days",
    "summary_chars",
    "text_for_embedding",
]

MIN_TEXT_LENGTH = 20


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return normalize_whitespace(str(value))


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def rebuild_text_for_embedding(row: pd.Series) -> str:
    """Compose the single document text that is embedded into ChromaDB.

    Keeping this in one place means the baseline and the corrupted flow build
    the same representation, so a metric delta is caused by the injected damage
    rather than by a different text template.
    """
    title = _text(row.get("title"))
    authors = _text(row.get("authors_joined"))
    published = _text(row.get("published"))
    categories = _text(row.get("categories_joined"))
    summary = _text(row.get("summary"))
    return compact_join(
        [
            f"Title: {title}" if title else "",
            f"Authors: {authors}" if authors else "",
            f"Published: {published}" if published else "",
            f"Categories: {categories}" if categories else "",
            f"Abstract: {summary}" if summary else "",
        ]
    )


def sort_newest_first(df: pd.DataFrame) -> pd.DataFrame:
    """Deterministic newest-first ordering (ties broken by ``paper_id``)."""
    work = df.copy()
    work["_published_dt"] = pd.to_datetime(work["published"], errors="coerce")
    work = work.sort_values(
        ["_published_dt", "paper_id"],
        ascending=[False, True],
        kind="mergesort",
        na_position="last",
    )
    return work.drop(columns=["_published_dt"])


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into an embedding-ready dataframe.

    1. Normalize title, summary, authors and categories.
    2. Parse published/updated dates into ISO ``YYYY-MM-DD``.
    3. Compute ``age_days = (run_date - published).days``.
    4. Build helper columns (``authors_joined``, ``categories_joined``,
       ``summary_chars``, ``text_for_embedding``).
    5. Drop duplicate ``paper_id`` values and unusable rows.
    6. Sort newest-first and return.
    """
    columns = [column for column in CLEAN_COLUMNS]
    if not records:
        return pd.DataFrame(columns=columns)

    if run_date.tzinfo is None:
        run_date = run_date.replace(tzinfo=timezone.utc)
    run_day = run_date.astimezone(timezone.utc).date()

    rows: list[dict[str, Any]] = []
    for record in records:
        paper_id = _text(record.paper_id)
        title = _text(record.title)
        summary = _text(record.summary)
        authors_joined = compact_join([_text(author) for author in record.authors], sep="; ")
        categories_joined = compact_join([_text(category) for category in record.categories], sep="; ")

        published_date = _parse_date(record.published)
        published = published_date.isoformat() if published_date else ""
        updated_date = _parse_date(record.updated)
        updated = updated_date.isoformat() if updated_date else published
        age_days = max(0, (run_day - published_date).days) if published_date else 0

        primary_category = _text(record.primary_category)
        if not primary_category and record.categories:
            primary_category = _text(record.categories[0])
        abs_url = _text(record.abs_url)
        pdf_url = _text(record.pdf_url) or abs_url

        row: dict[str, Any] = {
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors_joined": authors_joined,
            "categories_joined": categories_joined,
            "primary_category": primary_category,
            "published": published,
            "updated": updated,
            "abs_url": abs_url,
            "pdf_url": pdf_url,
            "age_days": int(age_days),
            "summary_chars": len(summary),
        }
        row["text_for_embedding"] = rebuild_text_for_embedding(pd.Series(row))
        rows.append(row)

    df = pd.DataFrame(rows, columns=columns)

    # Fail closed on unusable documents before anything reaches the vector store.
    df = df[df["paper_id"].astype(str).str.strip() != ""]
    df = df[df["title"].astype(str).str.strip() != ""]
    df = df[df["text_for_embedding"].astype(str).str.len() >= MIN_TEXT_LENGTH]
    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    df = df[df["published"].astype(str).str.strip() != ""]

    df = sort_newest_first(df).reset_index(drop=True)
    return df[columns]
