"""Conservative, auditable listing deduplication."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from ml.src.data_schema import canonicalize_url, normalize_for_matching


def _fingerprint(row: dict[str, Any]) -> str | None:
    fields = [row.get("title_raw"), row.get("city"), row.get("neighborhood"), row.get("surface_m2"), row.get("bedrooms"), row.get("bathrooms"), row.get("price_mad"), row.get("property_type")]
    if not row.get("title_raw") or sum(value is not None and str(value) != "" for value in fields) < 6:
        return None
    normalized = "|".join(normalize_for_matching(value) for value in fields)
    return hashlib.sha256(normalized.encode()).hexdigest()


def mark_duplicates(rows: list[dict[str, Any]]) -> dict[str, int]:
    seen_listing_ids: dict[str, str] = {}
    seen_ids: dict[tuple[str, str], str] = {}
    seen_urls: dict[str, str] = {}
    seen_fingerprints: dict[str, str] = {}
    fuzzy_blocks: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    counts = {"listing_id": 0, "source_id": 0, "url": 0, "fingerprint": 0, "fuzzy": 0}
    for index, row in enumerate(rows):
        source_id = row.get("source_listing_id")
        source_key = (normalize_for_matching(row.get("source")), normalize_for_matching(source_id))
        canonical_url = canonicalize_url(row.get("url"))
        fingerprint = _fingerprint(row)
        duplicate_of = None
        method = None
        if row["listing_id"] in seen_listing_ids:
            duplicate_of, method = seen_listing_ids[row["listing_id"]], "listing_id"
        elif source_id and source_key in seen_ids:
            duplicate_of, method = seen_ids[source_key], "source_id"
        elif canonical_url and canonical_url in seen_urls:
            duplicate_of, method = seen_urls[canonical_url], "url"
        elif fingerprint and fingerprint in seen_fingerprints:
            duplicate_of, method = seen_fingerprints[fingerprint], "fingerprint"
        if duplicate_of:
            row["deduplication_status"] = f"duplicate_{method}"
            row["duplicate_of"] = duplicate_of
            counts[method] += 1
            continue
        listing_id = row["listing_id"]
        seen_listing_ids[listing_id] = listing_id
        if source_id:
            seen_ids[source_key] = listing_id
        if canonical_url:
            seen_urls[canonical_url] = listing_id
        if fingerprint:
            seen_fingerprints[fingerprint] = listing_id
        block = (normalize_for_matching(row.get("city")), str(round(float(row.get("surface_m2") or 0) / 5) * 5), str(round(float(row.get("price_mad") or 0) / 50_000) * 50_000))
        fuzzy_blocks[block].append(index)

    # Only compare small, tightly constrained blocks; this avoids aggressive merges.
    for indexes in fuzzy_blocks.values():
        if len(indexes) < 2 or len(indexes) > 30:
            continue
        for position, left_index in enumerate(indexes):
            left = rows[left_index]
            if left["deduplication_status"] != "unique":
                continue
            left_text = normalize_for_matching(" ".join(filter(None, [left.get("title_raw"), left.get("location_raw")])))
            if len(left_text) < 18:
                continue
            for right_index in indexes[position + 1:]:
                right = rows[right_index]
                if right["deduplication_status"] != "unique" or normalize_for_matching(left.get("source")) == normalize_for_matching(right.get("source")):
                    continue
                right_text = normalize_for_matching(" ".join(filter(None, [right.get("title_raw"), right.get("location_raw")])))
                if len(right_text) >= 18 and SequenceMatcher(None, left_text, right_text).ratio() >= 0.96:
                    right["deduplication_status"] = "duplicate_fuzzy"
                    right["duplicate_of"] = left["listing_id"]
                    counts["fuzzy"] += 1
    return counts
