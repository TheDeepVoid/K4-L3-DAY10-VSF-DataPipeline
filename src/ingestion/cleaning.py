from __future__ import annotations

from datetime import datetime

import pandas as pd

from ingestion.crossref import PaperRecord
from core.utils import compact_join, normalize_whitespace, write_csv, write_json


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
   """Normalize raw records and create the embedding-ready dataframe."""
   rows: list[dict] = []
   run_day = run_date.date()
   for record in records:
      title = normalize_whitespace(record.title)
      summary = normalize_whitespace(record.summary)
      authors = [normalize_whitespace(author) for author in record.authors if normalize_whitespace(author)]
      categories = [normalize_whitespace(category) for category in record.categories if normalize_whitespace(category)]
      published = pd.to_datetime(record.published, errors="coerce", utc=True)
      if not record.paper_id or not title or not summary or pd.isna(published):
         continue
      published_day = published.date()
      authors_joined = compact_join(authors)
      categories_joined = compact_join(categories)
      rows.append(
         {
            "paper_id": record.paper_id.strip().lower(),
            "title": title,
            "summary": summary,
            "authors": authors,
            "categories": categories,
            "primary_category": normalize_whitespace(record.primary_category),
            "published": published_day.isoformat(),
            "updated": record.updated,
            "abs_url": record.abs_url,
            "pdf_url": record.pdf_url,
            "comment": record.comment,
            "authors_joined": authors_joined,
            "categories_joined": categories_joined,
            "summary_chars": len(summary),
            "age_days": max(0, (run_day - published_day).days),
            "text_for_embedding": "\n".join(
               [
                  f"Title: {title}",
                  f"Authors: {authors_joined}",
                  f"Published: {published_day.isoformat()}",
                  f"Categories: {categories_joined}",
                  f"Summary: {summary}",
               ]
            ),
         }
      )
   dataframe = pd.DataFrame(rows).drop_duplicates(subset=["paper_id"], keep="first")
   if not dataframe.empty:
      dataframe = dataframe.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
   return dataframe
