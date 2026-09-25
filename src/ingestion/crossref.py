from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import logging
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

logger = logging.getLogger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_API_ATTEMPTS = 3
API_TIMEOUT_SECONDS = 30
_TAG_RE = re.compile(r"<[^>]+>")


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


def _clean_text(value: Any) -> str:
    """Strip JATS/XML tags, unescape entities and collapse whitespace."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value if item)
    text = _TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    return normalize_whitespace(text)


def _as_date_str(value: Any) -> str:
    """Normalize the many Crossref date shapes into ``YYYY-MM-DD``."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return ""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
            return candidate
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", candidate)
        if match:
            return "-".join(match.groups())
        return ""
    if isinstance(value, dict):
        date_parts = value.get("date-parts")
        if date_parts:
            parts = date_parts[0] if isinstance(date_parts[0], (list, tuple)) else date_parts
            numbers = [int(part) for part in parts if isinstance(part, int)]
            if numbers:
                year = numbers[0]
                month = numbers[1] if len(numbers) > 1 else 1
                day = numbers[2] if len(numbers) > 2 else 1
                return f"{year:04d}-{month:02d}-{day:02d}"
        date_time = value.get("date-time")
        if isinstance(date_time, str):
            return _as_date_str(date_time)
    return ""


def _extract_authors(raw_authors: Any) -> list[str]:
    if not raw_authors:
        return []
    names: list[str] = []
    for author in raw_authors:
        if isinstance(author, dict):
            literal = _clean_text(author.get("name", ""))
            if literal:
                names.append(literal)
                continue
            given = _clean_text(author.get("given", ""))
            family = _clean_text(author.get("family", ""))
            name = normalize_whitespace(f"{given} {family}")
        else:
            name = _clean_text(author)
        if name:
            names.append(name)
    return names


def _extract_subjects(raw_subjects: Any) -> list[str]:
    if not raw_subjects:
        return []
    subjects: list[str] = []
    for subject in raw_subjects:
        value = _clean_text(subject)
        if value:
            subjects.append(value)
    return subjects


def _extract_pdf_url(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("link", []) or []:
        if not isinstance(link, dict):
            continue
        if str(link.get("content-type", "")).lower() == "application/pdf" and link.get("URL"):
            return str(link["URL"])
    return item.get("pdf_url") or fallback


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Accept a Crossref envelope, a bare item list, or a ``items`` payload."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    message = payload.get("message")
    if isinstance(message, dict):
        items = message.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    items = payload.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _record_from_item(item: dict[str, Any]) -> PaperRecord | None:
    """Build a PaperRecord from either a Crossref item or a normalized record."""
    if "paper_id" in item:
        paper_id = _clean_text(item.get("paper_id"))
        title = _clean_text(item.get("title"))
        summary = _clean_text(item.get("summary"))
        published = _as_date_str(item.get("published"))
        updated = _as_date_str(item.get("updated"))
        abs_url = _clean_text(item.get("abs_url"))
        raw_authors = item.get("authors")
        raw_categories = item.get("categories")
        authors = [
            _clean_text(author) if not isinstance(author, dict) else _clean_text(author.get("name", ""))
            for author in (raw_authors or [])
        ]
        categories = [_clean_text(category) for category in (raw_categories or [])]
        primary_category = _clean_text(item.get("primary_category"))
        pdf_url = _clean_text(item.get("pdf_url")) or abs_url
        comment = _clean_text(item.get("comment"))
    else:
        paper_id = _clean_text(item.get("DOI"))
        title = _clean_text(item.get("title"))
        summary = _clean_text(item.get("abstract"))
        authors = _extract_authors(item.get("author"))
        categories = _extract_subjects(item.get("subject"))
        primary_category = _clean_text(item.get("primary_category")) or (
            categories[0] if categories else ""
        )
        published = _as_date_str(item.get("published")) or _as_date_str(item.get("issued"))
        updated = (
            _as_date_str(item.get("updated"))
            or _as_date_str(item.get("created"))
            or _as_date_str(item.get("deposited"))
            or published
        )
        abs_url = _clean_text(item.get("URL"))
        pdf_url = _extract_pdf_url(item, abs_url)
        comment = _clean_text(item.get("comment"))

    if not paper_id or not title:
        logger.warning("Skipping malformed Crossref record (missing DOI or title).")
        return None

    return PaperRecord(
        paper_id=paper_id,
        title=title,
        summary=summary,
        authors=[author for author in authors if author],
        categories=[category for category in categories if category],
        primary_category=primary_category or (categories[0] if categories else ""),
        published=published,
        updated=updated,
        abs_url=abs_url,
        pdf_url=pdf_url,
        comment=comment,
    )


def parse_crossref_payload(payload: dict | list) -> list[PaperRecord]:
    """Parse a Crossref payload into a de-duplicated list of ``PaperRecord``.

    The raw snapshot may already contain normalized records (written by
    :func:`fetch_source_records`) or a pristine Crossref ``message.items``
    envelope. Both shapes are accepted so offline and live modes share one code
    path, which keeps the pipeline idempotent.
    """
    records: list[PaperRecord] = []
    seen: set[str] = set()
    for item in _extract_items(payload):
        record = _record_from_item(item)
        if record is None:
            continue
        key = record.paper_id.lower()
        if key in seen:
            logger.debug("Skipping duplicate paper_id %s", record.paper_id)
            continue
        seen.add(key)
        records.append(record)
    return records


def _request_crossref_payload(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": str(settings.max_results),
    }
    last_error: Exception | None = None
    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL,
                params=params,
                timeout=API_TIMEOUT_SECONDS,
                headers={"User-Agent": "day10-data-observability-lab/0.1 (mailto:student@example.com)"},
            )
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("Crossref request failed (attempt %s/%s): %s", attempt, MAX_API_ATTEMPTS, exc)
            time.sleep(min(2**attempt, 8))
            continue
        if response.status_code in RETRYABLE_STATUS_CODES:
            last_error = RuntimeError(f"Crossref returned HTTP {response.status_code}")
            logger.warning(
                "Crossref retryable status %s (attempt %s/%s).",
                response.status_code,
                attempt,
                MAX_API_ATTEMPTS,
            )
            time.sleep(min(2**attempt, 8))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Crossref API unavailable after {MAX_API_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref records, preserving both raw artifacts.

    Offline mode (default) reuses ``data/raw/crossref_response.json`` so the lab
    is reproducible without network access. Set ``REFRESH_SOURCE=1`` to hit the
    live REST API; a live response is only persisted when it parses into at
    least one valid record, which protects the trusted snapshot from a bad run.
    """
    snapshot_path = settings.paths.raw_api_response
    records_path = settings.paths.raw_records_json
    source = "local-snapshot"

    payload: Any = None
    if settings.refresh_source:
        try:
            payload = _request_crossref_payload(settings)
            source = "crossref-live-api"
        except Exception as exc:  # noqa: BLE001 - any failure falls back to snapshot
            logger.warning("Falling back to local snapshot: %s", exc)
            payload = None

    if payload is None:
        if not snapshot_path.exists():
            raise FileNotFoundError(
                f"Local Crossref snapshot not found at {snapshot_path}. "
                "Run with REFRESH_SOURCE=1 to download it from the API."
            )
        payload = read_json(snapshot_path)

    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError(
            f"No valid Crossref records could be parsed from {source}. Refusing to overwrite raw artifacts."
        )

    if source == "crossref-live-api":
        write_json(snapshot_path, payload)
        write_json(records_path, [asdict(record) for record in records])
    elif not records_path.exists():
        # Offline mode must never degrade the trusted raw artifacts: the shipped
        # snapshot can carry fields (e.g. `comment`) that the API response omits.
        write_json(records_path, [asdict(record) for record in records])
    else:
        logger.info("Keeping the existing raw records snapshot at %s", records_path)

    logger.info("Resolved %s records from %s", len(records), source)
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a raw JSON snapshot and map it to ``PaperRecord`` objects."""
    payload = read_json(Path(path))
    records = parse_crossref_payload(payload)
    logger.info("Loaded %s raw records from %s", len(records), path)
    return records
