"""Independent, policy-gated source adapters.

Live portal collection is disabled unless a source has both ``enabled=true``
and a non-empty ``authorization_reference`` in the user's local configuration.
The generic HTML collector favors JSON-LD and structured metadata, and can be
specialized through selectors without browser automation.
"""
from __future__ import annotations

import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .checkpoints import JsonlCheckpoint, record_key
from .schema import canonical_url, clean_text


USER_AGENT = "MaisonDeLUXResearchBot/3.0 (+contact required; respectful research collector)"


@dataclass
class SourceSpec:
    name: str
    kind: str
    source_label: str | None = None
    enabled: bool = False
    authorization_reference: str | None = None
    base_url: str | None = None
    robots_url: str | None = None
    terms_url: str | None = None
    input_paths: list[str] = field(default_factory=list)
    search_urls: list[str] = field(default_factory=list)
    max_pages: int = 1
    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 4.0
    concurrency: int = 5
    detail_budget_ratio: float = 0.25
    link_pattern: str = r"/(?:a|annonce|property|listing)/?\d+"
    selectors: dict[str, str] = field(default_factory=dict)
    policy_note: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceSpec":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in allowed})


class RespectfulHttpClient:
    def __init__(self, spec: SourceSpec, *, timeout: int = 30, retries: int = 2):
        self.spec = spec
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "fr,en;q=0.8"})
        self._lock = threading.Lock()
        self._next_request_at = 0.0

    def _wait_turn(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + random.uniform(
                self.spec.min_delay_seconds, self.spec.max_delay_seconds
            )
        if delay:
            time.sleep(delay)

    def get(self, url: str) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._wait_turn()
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code in {401, 403, 429}:
                    raise PermissionError(f"{self.spec.name} returned stop status HTTP {response.status_code}")
                if response.status_code >= 500 and attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                response.raise_for_status()
                return response
            except PermissionError:
                raise
            except requests.RequestException as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"request failed after retries for {url}: {last_error}")


def _walk_json(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json(nested)


def _jsonld_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.get_text(strip=True))
        except (json.JSONDecodeError, TypeError):
            continue
        objects.extend(_walk_json(payload))
    return objects


def _embedded_json_objects(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Read hydration/embedded API payloads without executing page JavaScript."""
    objects: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/json"], script#__NEXT_DATA__, script#__NUXT_DATA__'):
        try:
            payload = json.loads(script.get_text(strip=True))
        except (json.JSONDecodeError, TypeError):
            continue
        objects.extend(_walk_json(payload))
    return objects


def _real_estate_object(objects: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred = {
        "realestatelisting", "apartment", "house", "singlefamilyresidence",
        "residence", "product", "accommodation",
    }
    for obj in objects:
        object_type = obj.get("@type")
        types = object_type if isinstance(object_type, list) else [object_type]
        if any(str(item).casefold() in preferred for item in types if item):
            return obj
    # Hydration/API data often omits schema.org @type. Require several listing
    # keys to avoid confusing site-wide configuration with an observation.
    candidates: list[tuple[int, dict[str, Any]]] = []
    evidence_keys = {
        "url", "canonicalUrl", "title", "name", "price", "surface", "area",
        "city", "location", "address", "bedrooms", "datePosted", "publishedAt",
    }
    for obj in objects:
        score = len(evidence_keys.intersection(obj))
        if score >= 4:
            candidates.append((score, obj))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _deep_first(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] not in (None, ""):
                return value[key]
        for nested in value.values():
            found = _deep_first(nested, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _deep_first(nested, keys)
            if found not in (None, ""):
                return found
    return None


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if node and node.get("content"):
            return clean_text(node["content"])
    return None


def parse_detail_html(html: str, url: str, source: str, selectors: dict[str, str] | None = None) -> dict[str, Any]:
    selectors = selectors or {}
    soup = BeautifulSoup(html, "html.parser")
    objects = _jsonld_objects(soup) + _embedded_json_objects(soup)
    obj = _real_estate_object(objects) or {}
    offered = obj.get("itemOffered") if isinstance(obj.get("itemOffered"), dict) else obj
    offer = obj.get("offers") if isinstance(obj.get("offers"), dict) else offered.get("offers", {}) if isinstance(offered, dict) else {}
    address = offered.get("address", {}) if isinstance(offered, dict) else {}
    if isinstance(address, str):
        address = {"streetAddress": address}
    geo = offered.get("geo", {}) if isinstance(offered, dict) else {}
    floor_size = offered.get("floorSize", {}) if isinstance(offered, dict) else {}
    seller = obj.get("seller", {}) if isinstance(obj.get("seller"), dict) else {}

    def selected(name: str) -> str | None:
        selector = selectors.get(name)
        node = soup.select_one(selector) if selector else None
        return clean_text(node.get_text(" ", strip=True)) if node else None

    canonical = soup.find("link", rel="canonical")
    record_url = canonical_url(obj.get("url") or (canonical.get("href") if canonical else None) or url)
    time_node = soup.select_one('time[datetime], [itemprop="datePublished"][datetime]')
    modified_node = soup.select_one('[itemprop="dateModified"][datetime]')
    obj_url = obj.get("url") or obj.get("canonicalUrl") or obj.get("canonical_url") or obj.get("listingUrl")
    record: dict[str, Any] = {
        "source": source,
        "url": canonical_url(obj_url or record_url),
        "source_listing_id": clean_text(_deep_first(obj, ("sku", "productID", "listingId", "listing_id", "reference", "ref")) or selected("source_listing_id")),
        "title_raw": clean_text(_deep_first(obj, ("name", "title", "headline")) or selected("title") or _meta(soup, "og:title")),
        "description_raw": clean_text(_deep_first(obj, ("description", "summary")) or selected("description") or _meta(soup, "description", "og:description")),
        "publication_date": clean_text(_deep_first(obj, ("datePosted", "datePublished", "publishedAt", "publicationDate", "createdAt")) or selected("publication_date") or (time_node.get("datetime") if time_node else None) or _meta(soup, "article:published_time")),
        "date_modified": clean_text(_deep_first(obj, ("dateModified", "updatedAt", "modifiedAt")) or (modified_node.get("datetime") if modified_node else None) or _meta(soup, "article:modified_time")),
        "price": (offer.get("price") if isinstance(offer, dict) else None) or _deep_first(obj, ("price", "amount")),
        "currency": (offer.get("priceCurrency") if isinstance(offer, dict) else None) or _deep_first(obj, ("priceCurrency", "currency")),
        "price_raw": selected("price"),
        "city": address.get("addressLocality") if isinstance(address, dict) else _deep_first(obj, ("city", "addressLocality")),
        "neighborhood": address.get("addressRegion") if isinstance(address, dict) else _deep_first(obj, ("neighborhood", "district", "quartier")),
        "location_raw": address.get("streetAddress") if isinstance(address, dict) else (_deep_first(obj, ("location", "addressText")) or selected("location")),
        "latitude": geo.get("latitude") if isinstance(geo, dict) else _deep_first(obj, ("latitude", "lat")),
        "longitude": geo.get("longitude") if isinstance(geo, dict) else _deep_first(obj, ("longitude", "lng", "lon")),
        "surface_m2": (floor_size.get("value") if isinstance(floor_size, dict) else None) or _deep_first(obj, ("surface_m2", "surface", "area")),
        "bedrooms": (offered.get("numberOfBedrooms") if isinstance(offered, dict) else None) or _deep_first(obj, ("bedrooms", "numberOfBedrooms")),
        "bathrooms": (offered.get("numberOfBathroomsTotal") if isinstance(offered, dict) else None) or _deep_first(obj, ("bathrooms", "numberOfBathroomsTotal")),
        "source_category": clean_text((offered.get("@type") if isinstance(offered, dict) else None) or _deep_first(obj, ("propertyType", "property_type", "category"))) or selected("property_type"),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
    if not record["source_listing_id"] and record_url:
        match = re.search(r"(?:^|/)(\d{4,})(?:/|-|$)", record_url)
        if match:
            record["source_listing_id"] = match.group(1)
    return record


def extract_listing_links(html: str, page_url: str, link_pattern: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for obj in _jsonld_objects(soup):
        candidate = obj.get("url")
        if candidate:
            links.append(urljoin(page_url, str(candidate)))
    for node in soup.select("a[href]"):
        candidate = urljoin(page_url, node.get("href"))
        if re.search(link_pattern, candidate, re.I):
            links.append(candidate)
    return list(dict.fromkeys(filter(None, map(canonical_url, links))))


def extract_list_records(
    html: str,
    page_url: str,
    source: str,
    selectors: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Extract structured card evidence without opening detail pages."""
    selectors = selectors or {}
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    real_estate_types = {
        "realestatelisting", "apartment", "house", "singlefamilyresidence",
        "residence", "product", "accommodation",
    }
    for obj in _jsonld_objects(soup):
        object_type = obj.get("@type")
        types = object_type if isinstance(object_type, list) else [object_type]
        if not any(str(item).casefold() in real_estate_types for item in types if item):
            continue
        fake_html = f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'
        record = parse_detail_html(fake_html, page_url, source)
        url = canonical_url(record.get("url"))
        if url and url != canonical_url(page_url) and url not in seen_urls:
            record["collection_level"] = "list_jsonld"
            record["source_page_url"] = page_url
            records.append(record)
            seen_urls.add(url)

    card_selector = selectors.get("card")
    if not card_selector:
        return records

    def card_text(card: Any, name: str) -> str | None:
        selector = selectors.get(name)
        node = card.select_one(selector) if selector else None
        return clean_text(node.get_text(" ", strip=True)) if node else None

    for position, card in enumerate(soup.select(card_selector), start=1):
        link_selector = selectors.get("link", "a[href]")
        link = card.select_one(link_selector)
        url = canonical_url(urljoin(page_url, link.get("href"))) if link and link.get("href") else None
        if not url or url in seen_urls:
            continue
        record = {
            "source": source,
            "url": url,
            "source_listing_id": card.get(selectors.get("source_listing_id_attribute", "data-id")),
            "title_raw": card_text(card, "title"),
            "price_raw": card_text(card, "price"),
            "location_raw": card_text(card, "location"),
            "surface_m2": card_text(card, "surface"),
            "bedrooms": card_text(card, "bedrooms"),
            "bathrooms": card_text(card, "bathrooms"),
            "publication_date": card_text(card, "publication_date"),
            "source_category": card_text(card, "property_type"),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "collection_level": "list_dom",
            "source_page_url": page_url,
            "position_on_page": position,
        }
        records.append(record)
        seen_urls.add(url)
    return records


def load_file_records(path: Path, forced_source: str | None = None) -> list[dict[str, Any]]:
    suffix = path.suffix.casefold()
    if suffix == ".parquet":
        rows = pd.read_parquet(path).to_dict("records")
    elif suffix == ".csv":
        rows = pd.read_csv(path, low_memory=False).to_dict("records")
    elif suffix in {".jsonl", ".ndjson"}:
        with path.open(encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    elif suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("records", [])
    else:
        raise ValueError(f"unsupported feed type: {path}")
    for index, row in enumerate(rows, start=1):
        if forced_source:
            row["source"] = forced_source
        row["source_record_path"] = f"{path.as_posix()}#row={index}"
    return rows


def collect_file_source(spec: SourceSpec, root: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if spec.kind == "authorized_feed" and not clean_text(spec.authorization_reference):
        raise PermissionError(
            f"{spec.name} is disabled until a written contract/export authorization is recorded"
        )
    records: list[dict[str, Any]] = []
    for pattern in spec.input_paths:
        candidates = sorted(root.glob(pattern))
        if not candidates and (root / pattern).exists():
            candidates = [root / pattern]
        for path in candidates:
            forced = None if spec.name == "preserved_local_evidence" else (spec.source_label or spec.name)
            records.extend(load_file_records(path, forced_source=forced))
            if limit and len(records) >= limit:
                return records[:limit]
        if spec.name == "preserved_local_evidence" and records:
            # The tracked sample is a portable fallback, not an additional
            # observation source to concatenate with the local full corpus.
            return records
    return records[:limit] if limit else records


def _expanded_pages(spec: SourceSpec) -> list[str]:
    pages: list[str] = []
    # Page-major ordering prevents the first (usually largest) city from
    # consuming the collection budget before secondary cities are attempted.
    for page in range(1, spec.max_pages + 1):
        for template in spec.search_urls:
            if "{page}" in template:
                pages.append(template.format(page=page))
            elif page == 1:
                pages.append(template)
    return list(dict.fromkeys(pages))


def _robots_allows(spec: SourceSpec, client: RespectfulHttpClient, urls: Iterable[str]) -> None:
    if not spec.robots_url:
        raise PermissionError(f"{spec.name}: robots_url is required for live collection")
    response = client.get(spec.robots_url)
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    denied = [url for url in urls if not parser.can_fetch(USER_AGENT, url)]
    if denied:
        raise PermissionError(f"{spec.name}: robots.txt denies {denied[0]}")


def collect_live_source(
    spec: SourceSpec,
    checkpoint: JsonlCheckpoint,
    *,
    mode: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    if not spec.enabled or not clean_text(spec.authorization_reference):
        raise PermissionError(f"{spec.name} is disabled until written/API authorization is recorded")
    pages = _expanded_pages(spec)
    if not pages:
        raise ValueError(f"{spec.name}: configure at least one authorized search URL")
    client = RespectfulHttpClient(spec)
    _robots_allows(spec, client, pages)

    portal_source = spec.source_label or spec.name
    cards: dict[str, dict[str, Any]] = {}
    for page_number, page_url in enumerate(pages, start=1):
        response = client.get(page_url)
        page_records = extract_list_records(response.text, page_url, portal_source, spec.selectors)
        for raw in page_records:
            url = canonical_url(raw.get("url"))
            if url:
                cards.setdefault(url, raw)
        for url in extract_listing_links(response.text, page_url, spec.link_pattern):
            cards.setdefault(url, {
                "source": portal_source, "url": url, "source_page_url": page_url,
                "search_page_number": page_number, "scraped_at": datetime.now(timezone.utc).isoformat(),
                "collection_level": "list_link",
            })
        print(f"[{spec.name}] pages={page_number}/{len(pages)} cards={len(cards)}")
        if limit and len(cards) >= limit * 2:
            break

    records = list(cards.values())
    if limit:
        records = records[:limit]
    existing_keys = checkpoint.keys
    records = [row for row in records if record_key(row) not in existing_keys]

    def missing_score(row: dict[str, Any]) -> int:
        fields = ("publication_date", "source_category", "price", "price_raw", "surface_m2", "city", "location_raw", "description_raw")
        return sum(not clean_text(row.get(field)) for field in fields)

    if mode == "FULL":
        detail_budget = len(records)
    else:
        detail_budget = min(len(records), max(0, int(len(records) * max(0.0, min(spec.detail_budget_ratio, 1.0)))))
    detail_urls = {
        row["url"] for row in sorted(records, key=missing_score, reverse=True)[:detail_budget]
        if row.get("url")
    }
    concurrency = max(1, min(spec.concurrency, 15))
    enriched: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(client.get, url): url for url in detail_urls}
        for future in as_completed(futures):
            url = futures[future]
            response = future.result()
            enriched[url] = parse_detail_html(response.text, url, portal_source, spec.selectors)

    collected: list[dict[str, Any]] = []
    for card in records:
        detail = enriched.get(card.get("url"), {})
        merged = dict(card)
        for key, value in detail.items():
            if clean_text(value):
                merged[key] = value
        merged["collection_level"] = "detail" if detail else merged.get("collection_level", "list")
        merged["source_record_path"] = checkpoint.path.as_posix()
        collected.append(merged)
    for start in range(0, len(collected), 100):
        checkpoint.append_batch(collected[start:start + 100])
    print(f"[{spec.name}] records={len(collected)} detail_pages={len(enriched)} mode={mode}")
    resumed = checkpoint.read()
    return resumed[:limit] if limit else resumed


def collect_sources(
    specs: list[SourceSpec],
    root: Path,
    checkpoint_dir: Path,
    *,
    mode: str,
    target: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    records_by_name: dict[str, list[dict[str, Any]]] = {}
    statuses: dict[str, str] = {}
    active_specs = [spec for spec in specs if spec.enabled]
    per_source = max(1, target // max(1, len(active_specs)))

    def collect_one(spec: SourceSpec) -> tuple[list[dict[str, Any]], str]:
        started_at = time.monotonic()
        try:
            if spec.kind in {"file", "authorized_feed"}:
                file_limit = None if spec.name == "preserved_local_evidence" else (per_source if mode == "PILOT" else None)
                source_records = collect_file_source(spec, root, file_limit)
                elapsed = time.monotonic() - started_at
                print(f"[{spec.name}] records={len(source_records)} elapsed={elapsed:.2f}s")
                return source_records, f"loaded:{len(source_records)}:elapsed_seconds={elapsed:.2f}"
            elif spec.kind == "live_html":
                checkpoint = JsonlCheckpoint(checkpoint_dir / f"{spec.name}.jsonl")
                source_records = collect_live_source(spec, checkpoint, mode=mode, limit=per_source)
                elapsed = time.monotonic() - started_at
                return source_records, f"collected:{len(source_records)}:elapsed_seconds={elapsed:.2f}"
            else:
                return [], f"unsupported_kind:{spec.kind}"
        except Exception as error:
            return [], f"blocked:{type(error).__name__}:{error}"

    for spec in specs:
        if not spec.enabled:
            statuses[spec.name] = "disabled"
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(active_specs)))) as pool:
        futures = {pool.submit(collect_one, spec): spec for spec in active_specs}
        for future in as_completed(futures):
            spec = futures[future]
            source_records, status = future.result()
            records_by_name[spec.name] = source_records
            statuses[spec.name] = status
    records: list[dict[str, Any]] = []
    for spec in specs:
        records.extend(records_by_name.get(spec.name, []))
    return records, statuses
