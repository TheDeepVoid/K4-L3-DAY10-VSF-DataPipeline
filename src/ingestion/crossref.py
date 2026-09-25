from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import html
import json
from pathlib import Path
import re

import requests

from core.config import Settings
from core.utils import normalize_whitespace, write_json


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref work-list payloads into normalized paper records."""
    def clean_text(value: object) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        return normalize_whitespace(text)

    def parse_date(item: dict, *keys: str) -> str:
        for key in keys:
            value = item.get(key, {})
            parts = value.get("date-parts", [[]]) if isinstance(value, dict) else [[]]
            parts = parts[0] if parts else []
            if parts:
                year, month, day = (parts + [1, 1])[:3]
                return date(int(year), int(month), int(day)).isoformat()
            if isinstance(value, dict) and value.get("date-time"):
                return str(value["date-time"])[:10]
        return ""

    records: list[PaperRecord] = []
    for item in payload.get("message", {}).get("items", []):
        doi = clean_text(item.get("DOI")).lower()
        doi = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", doi)
        doi = re.sub(r"^doi:\s*", "", doi).strip()
        title = clean_text((item.get("title") or [""])[0])
        summary = clean_text(item.get("abstract"))
        if not doi or not title or not summary:
            continue
        authors = [
            clean_text(" ".join(filter(None, [author.get("given"), author.get("family")])).strip())
            for author in item.get("author", [])
        ]
        authors = [author for author in authors if author]
        categories = [clean_text(subject) for subject in item.get("subject", [])]
        categories = [category for category in categories if category]
        published = parse_date(item, "published", "issued", "created")
        updated = parse_date(item, "updated", "created") or published
        url = clean_text(item.get("URL")) or f"https://doi.org/{doi}"
        pdf_url = next(
            (clean_text(link.get("URL")) for link in item.get("link", []) if link.get("content-type") == "application/pdf"),
            url,
        )
        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=updated,
                abs_url=url,
                pdf_url=pdf_url,
                comment=f"Crossref record {doi}",
            )
        )
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref data, falling back to the bundled snapshot offline."""
    payload: dict | None = None
    if settings.refresh_source:
        try:
            response = requests.get(
                "https://api.crossref.org/works",
                params={"query": settings.source_query, "filter": settings.source_filter, "rows": settings.max_results},
                headers={"User-Agent": "AI20K-data-observability-lab/1.0"},
                timeout=15,
            )
            if response.status_code == 429:
                raise requests.HTTPError("Crossref rate limit", response=response)
            response.raise_for_status()
            payload = response.json()
            write_json(settings.paths.raw_api_response, payload)
        except (OSError, requests.RequestException, ValueError):
            payload = None
    if payload is None:
        payload = json.loads(settings.paths.raw_api_response.read_text(encoding="utf-8"))

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [record.__dict__ for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load normalized raw records written by :func:`fetch_source_records`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [PaperRecord(**item) for item in payload]
