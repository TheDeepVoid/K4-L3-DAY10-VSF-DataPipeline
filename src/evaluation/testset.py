from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class TestSet:
   samples: list[dict[str, Any]]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
   """Create one deterministic benchmark question for each required type."""
   if len(df) < 5:
      raise ValueError("At least five cleaned papers are required to build the benchmark.")

   rows = df.reset_index(drop=True).iloc[:5]
   first, second, third, fourth, fifth = (row for _, row in rows.iterrows())
   samples = [
      {
         "id": "q-summary-001",
         "type": "summary",
         "question_type": "summary",
         "question": f"What is the main research contribution of '{first['title']}'?",
         "ground_truth": first["summary"],
         "ground_truth_doc_ids": [first["paper_id"]],
      },
      {
         "id": "q-authors-001",
         "type": "authors",
         "question_type": "authors",
            "question": f"Who authored the study '{second['title']}'?",
         "ground_truth": second["authors_joined"],
         "ground_truth_doc_ids": [second["paper_id"]],
      },
      {
         "id": "q-date-001",
         "type": "date",
         "question_type": "date",
         "question": f"When was '{third['title']}' published?",
         "ground_truth": third["published"],
         "ground_truth_doc_ids": [third["paper_id"]],
      },
      {
         "id": "q-category-001",
         "type": "category",
         "question_type": "category",
            "question": f"What categories does '{fourth['title']}' belong to?",
         "ground_truth": fourth["categories_joined"],
         "ground_truth_doc_ids": [fourth["paper_id"]],
      },
      {
         "id": "q-multi-hop-001",
         "type": "multi_hop",
         "question_type": "multi_hop",
         "question": (
            f"Compare the research focus of '{fifth['title']}' and '{first['title']}', "
            "including the specialist fields represented by both papers."
         ),
         "ground_truth": (
            f"{fifth['title']}: {fifth['categories_joined']}. "
            f"{first['title']}: {first['categories_joined']}."
         ),
         "ground_truth_doc_ids": [fifth["paper_id"], first["paper_id"]],
      },
   ]
   path = Path(output_path)
   path.parent.mkdir(parents=True, exist_ok=True)
   path.write_text(json.dumps(samples, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
   return samples


def load_or_create_test_set(df: pd.DataFrame, output_path) -> TestSet:
   """Load an existing benchmark or create the deterministic five-sample set."""
   path = Path(output_path)
   if path.exists():
      samples = json.loads(path.read_text(encoding="utf-8"))
   else:
      samples = build_test_set(df, path)
   return TestSet(samples=samples)
