"""Safe, resumable Mubawab card collector for MaisonDeLUX Schema V2.

The Phase 5A default is deliberately bounded to 20 new records and writes to a
new V2 file. It never overwrites the historical training CSV.
"""
from __future__ import annotations

import argparse
import csv
import logging
import random
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

try:  # Works both as ``python ml/src/data.py`` and as an imported project module.
    from .data_schema import SCHEMA_V2_COLUMNS, build_v2_record
except ImportError:
    from data_schema import SCHEMA_V2_COLUMNS, build_v2_record

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "maisonlux_listings_v2.csv"
BASE_URL = "https://www.mubawab.ma/fr/sc/appartements-a-vendre"
SOURCE = "mubawab.ma"
LOGGER = logging.getLogger("maisonlux.collection")


def page_url(page: int) -> str:
    return BASE_URL if page == 1 else f"{BASE_URL}:p:{page}"


def fetch_html(session: requests.Session, url: str, timeout: float = 20,
               max_attempts: int = 3, retry_delay: float = 5) -> str | None:
    """Fetch one public page conservatively; do not bypass access controls."""
    for attempt in range(1, max_attempts + 1):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return response.text
            if response.status_code in {401, 403, 429}:
                LOGGER.error("Access/rate-limit response %s for %s; stopping retries", response.status_code, url)
                return None
            LOGGER.warning("HTTP %s for %s (attempt %s/%s)", response.status_code, url, attempt, max_attempts)
        except requests.RequestException as error:
            LOGGER.warning("Request failed for %s (attempt %s/%s): %s", url, attempt, max_attempts, error)
        if attempt < max_attempts:
            time.sleep(retry_delay)
    return None


def _text(element: Tag | None) -> str | None:
    return " ".join(element.get_text(" ", strip=True).split()) if element else None


def parse_listing_card(card: Tag, scraped_at: str | None = None) -> dict:
    """Extract evidence present on a result card; unavailable fields stay null."""
    title_element = card.select_one("h2.listingTit")
    link = title_element.find("a", href=True) if title_element else card.find("a", href=True)
    location_icon = card.select_one("i.icon-location")
    return {
        "native_id": card.get("data-id") or card.get("data-listing-id"),
        "url": urljoin(BASE_URL, link.get("href")) if link else None,
        "scraped_at": scraped_at,
        "source_category": "appartements à vendre",
        "title_raw": _text(title_element),
        "raw_price_text": _text(card.select_one("span.priceTag")),
        "location_raw": _text(location_icon.parent if location_icon else None),
        "details_raw": _text(card.select_one("div.adDetails")),
    }


def parse_result_page(html: str, scraped_at: str | None = None) -> list[dict]:
    records = []
    for position, card in enumerate(BeautifulSoup(html, "html.parser").select("div.listingBox"), start=1):
        try:
            raw = parse_listing_card(card, scraped_at)
            if not raw.get("title_raw"):
                LOGGER.warning("Skipping card %s: title missing", position)
                continue
            records.append(build_v2_record(raw, source=SOURCE))
        except (AttributeError, TypeError, ValueError) as error:
            LOGGER.exception("Card %s could not be parsed: %s", position, error)
    return records


def load_known_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["listing_id"] for row in csv.DictReader(handle) if row.get("listing_id")}


def append_records(path: Path, records: Iterable[dict], known_ids: set[str] | None = None) -> int:
    """Append only new stable IDs in fixed column order; each call is a checkpoint."""
    path.parent.mkdir(parents=True, exist_ok=True)
    known = known_ids if known_ids is not None else load_known_ids(path)
    new_records = [record for record in records if record.get("listing_id") not in known]
    if not new_records:
        return 0
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCHEMA_V2_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for record in new_records:
            writer.writerow({column: record.get(column) for column in SCHEMA_V2_COLUMNS})
            known.add(record["listing_id"])
        handle.flush()
    return len(new_records)


def collect(output: Path = DEFAULT_OUTPUT, max_pages: int = 1, max_listings: int = 20,
            min_delay: float = 2.0, max_delay: float = 4.0) -> int:
    """Collect a bounded number of public result-card records with checkpoints."""
    session = requests.Session()
    session.headers.update({"User-Agent": "MaisonDeLUX-PFE/1.0 educational-data-audit",
                            "Accept-Language": "fr-MA,fr;q=0.9"})
    known, collected = load_known_ids(output), 0
    for page in range(1, max_pages + 1):
        url = page_url(page)
        LOGGER.info("Fetching result page %s: %s", page, url)
        html = fetch_html(session, url)
        if html is None:
            LOGGER.error("Stopping collection after failed page %s", page); break
        records = parse_result_page(html)
        if not records:
            LOGGER.info("No listing cards found on page %s; stopping", page); break
        written = append_records(output, records[:max_listings - collected], known)
        collected += written
        LOGGER.info("Checkpoint: %s new records (%s total this run)", written, collected)
        if collected >= max_listings:
            break
        time.sleep(random.uniform(min_delay, max_delay))
    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect bounded Mubawab cards into Schema V2")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--max-listings", type=int, default=20)
    args = parser.parse_args()
    if args.max_pages < 1 or args.max_listings < 1:
        parser.error("--max-pages and --max-listings must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    LOGGER.info("Collection finished: %s new records", collect(args.output, args.max_pages, args.max_listings))


if __name__ == "__main__":
    main()
