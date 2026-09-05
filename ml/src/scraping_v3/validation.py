"""Property-aware quality rules and conservative multi-level deduplication."""
from __future__ import annotations

import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

from .geography import valid_neighborhood
from .schema import PROPERTY_TYPES, canonical_url, normalized


RESIDENTIAL = {"appartement", "maison", "villa", "riad", "studio", "duplex"}


def validate_record(row: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = [part for part in str(row.get("validation_reasons") or "").split("|") if part]
    hard: list[str] = []
    if row.get("transaction_type") != "sale":
        hard.append("rental_listing" if row.get("transaction_type") == "rent" else "unknown_transaction")
    if row.get("price_mad") is None:
        hard.append("missing_price_mad")
    elif not 25_000 <= float(row["price_mad"]) <= 2_000_000_000:
        hard.append("implausible_price")
    if row.get("surface_m2") is None:
        hard.append("missing_surface_m2")
    else:
        surface = float(row["surface_m2"])
        bounds = {
            "appartement": (12, 1_200), "studio": (10, 250), "duplex": (20, 1_500),
            "villa": (40, 20_000), "maison": (25, 10_000), "riad": (30, 10_000),
            "terrain": (20, 2_000_000), "immeuble": (40, 100_000), "bureau": (8, 20_000),
            "local commercial": (5, 100_000), "magasin": (5, 100_000), "other": (5, 2_000_000),
        }.get(row.get("property_type"), (5, 2_000_000))
        if not bounds[0] <= surface <= bounds[1]:
            reasons.append("suspicious_surface_for_property_type")
    if not row.get("city"):
        hard.append("missing_city")
    if not row.get("region"):
        hard.append("missing_region")
    if row.get("property_type") not in PROPERTY_TYPES or row.get("property_type") == "other":
        hard.append("unknown_property_type")
    if not valid_neighborhood(row.get("neighborhood"), row.get("city")):
        reasons.append("neighborhood_unavailable_or_invalid")

    for field, warning_threshold in (("bedrooms", 15), ("bathrooms", 12)):
        value = row.get(field)
        if value is not None and (float(value) < 0 or float(value) > warning_threshold):
            reasons.append(f"suspicious_{field}")
    if row.get("property_type") in RESIDENTIAL and row.get("surface_m2") and row.get("bedrooms"):
        if float(row["surface_m2"]) / max(float(row["bedrooms"]), 1) < 5:
            reasons.append("suspicious_surface_bedroom_ratio")
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if latitude is not None or longitude is not None:
        if latitude is None or longitude is None or not (20.0 <= float(latitude) <= 36.8 and -17.8 <= float(longitude) <= -0.5):
            hard.append("coordinates_outside_morocco")
    ppm2 = row.get("price_per_m2")
    if ppm2 is not None:
        broad_bounds = (200, 300_000) if row.get("property_type") in RESIDENTIAL else (10, 2_000_000)
        if not broad_bounds[0] <= float(ppm2) <= broad_bounds[1]:
            reasons.append("suspicious_price_per_m2")

    reasons = list(dict.fromkeys(reasons + hard))
    status = "rejected" if hard else "warning" if reasons else "valid"
    return status, reasons


def _fingerprint(row: dict[str, Any]) -> str | None:
    fields = [row.get(key) for key in ("city", "neighborhood", "property_type", "surface_m2", "bedrooms", "price_mad")]
    if sum(value is not None and str(value) != "" for value in fields) < 5:
        return None
    material = "|".join(normalized(value) for value in fields)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def mark_duplicates(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Mark exact duplicates and possible title matches; never silently merge."""
    seen_listing: dict[str, str] = {}
    seen_native: dict[tuple[str, str], str] = {}
    seen_url: dict[str, str] = {}
    seen_fingerprint: dict[str, str] = {}
    blocks: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    counts = {"listing_id": 0, "source_id": 0, "url": 0, "fingerprint": 0, "possible_text": 0}

    for index, row in enumerate(rows):
        listing_id = str(row.get("listing_id") or "")
        native = str(row.get("source_listing_id") or "")
        native_key = (normalized(row.get("source")), normalized(native))
        url = canonical_url(row.get("url"))
        fingerprint = _fingerprint(row)
        duplicate_of = None
        method = None
        if listing_id and listing_id in seen_listing:
            duplicate_of, method = seen_listing[listing_id], "listing_id"
        elif native and native_key in seen_native:
            duplicate_of, method = seen_native[native_key], "source_id"
        elif url and url in seen_url:
            duplicate_of, method = seen_url[url], "url"
        elif fingerprint and fingerprint in seen_fingerprint:
            duplicate_of, method = seen_fingerprint[fingerprint], "fingerprint"
        if duplicate_of:
            row["deduplication_status"] = f"duplicate_{method}"
            row["duplicate_of"] = duplicate_of
            counts[method] += 1
            continue
        row["deduplication_status"] = "unique"
        row["duplicate_of"] = None
        seen_listing[listing_id] = listing_id
        if native:
            seen_native[native_key] = listing_id
        if url:
            seen_url[url] = listing_id
        if fingerprint:
            seen_fingerprint[fingerprint] = listing_id
        block = (
            normalized(row.get("city")),
            str(round(float(row.get("surface_m2") or 0) / 5) * 5),
            str(round(float(row.get("price_mad") or 0) / 50_000) * 50_000),
        )
        blocks[block].append(index)

    # Level D is deliberately only a flag. It is never removed from the clean set
    # unless stronger Level A-C evidence exists.
    for indexes in blocks.values():
        if len(indexes) < 2 or len(indexes) > 40:
            continue
        for offset, left_index in enumerate(indexes):
            left = rows[left_index]
            if left["deduplication_status"] != "unique":
                continue
            left_text = normalized(left.get("title_raw"))
            if len(left_text) < 18:
                continue
            for right_index in indexes[offset + 1:]:
                right = rows[right_index]
                if right["deduplication_status"] != "unique" or normalized(left.get("source")) == normalized(right.get("source")):
                    continue
                right_text = normalized(right.get("title_raw"))
                if len(right_text) >= 18 and SequenceMatcher(None, left_text, right_text).ratio() >= 0.94:
                    right["deduplication_status"] = "possible_duplicate_text"
                    right["duplicate_of"] = left["listing_id"]
                    counts["possible_text"] += 1
    return counts


def validate_rows(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        status, reasons = validate_record(row)
        row["validation_status"] = status
        row["validation_reasons"] = "|".join(reasons)
