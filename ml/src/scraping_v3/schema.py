"""Canonical V3 schema and low-level parsing helpers.

The module deliberately keeps unavailable values null.  In particular,
``scraped_at`` is never substituted for ``publication_date`` and absent
amenities remain ``unknown`` rather than becoming ``no``.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


V3_COLUMNS = [
    "listing_id", "source", "source_listing_id", "url",
    "scraped_at", "publication_date", "publication_date_status",
    "transaction_type", "region", "city", "neighborhood", "latitude", "longitude",
    "property_type", "surface_m2", "land_surface_m2", "built_surface_m2",
    "bedrooms", "bathrooms", "floor", "total_floors",
    "price_mad", "price_raw", "price_per_m2",
    "furnished_status", "parking", "balcony", "terrace", "garden", "pool",
    "elevator", "garage", "security", "air_conditioning", "sea_view",
    "title_raw", "description_raw", "location_raw",
    "validation_status", "validation_reasons", "deduplication_status", "duplicate_of",
    "source_record_path",
]

AMENITY_COLUMNS = [
    "parking", "balcony", "terrace", "garden", "pool", "elevator", "garage",
    "security", "air_conditioning", "sea_view",
]

PROPERTY_TYPES = {
    "appartement", "maison", "villa", "riad", "studio", "duplex", "terrain",
    "immeuble", "bureau", "local commercial", "magasin", "other",
}


def missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().casefold() in {"", "nan", "none", "null", "<na>", "nat"}


def clean_text(value: Any) -> str | None:
    if missing(value):
        return None
    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or None


def normalized(value: Any) -> str:
    text = "" if missing(value) else unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text).strip()


def canonical_url(value: Any) -> str | None:
    value = clean_text(value)
    if not value:
        return None
    parts = urlsplit(value if "://" in value else f"https://{value}")
    if not parts.netloc:
        return None
    query = [
        (key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in {"fbclid", "gclid"}
    ]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.casefold() or "https", parts.netloc.casefold(), path, urlencode(query), ""))


def safe_float(value: Any) -> float | None:
    if missing(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:[.,]\d+)?", normalized(value).replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group().replace(",", "."))
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    parsed = safe_float(value)
    return int(parsed) if parsed is not None else None


def parse_price_mad(value: Any, explicit_currency: Any = None) -> tuple[float | None, str | None]:
    """Parse a total MAD price without inventing exchange rates."""
    raw = clean_text(value)
    if raw is None:
        return None, "missing_price"
    text = normalized(raw)
    if re.search(r"sur demande|a consulter|nous consulter|contact", text):
        return None, "price_on_request"
    currency = normalized(explicit_currency)
    if re.search(r"\beur\b|euro|€|\busd\b|dollar|\$", raw.casefold()) or currency in {"eur", "usd"}:
        return None, "non_mad_currency"
    if re.search(r"(?:/|par)\s*m(?:2|²)", raw.casefold()):
        return None, "unit_price_not_total"
    multiplier = 1.0
    if re.search(r"\bm(?:illion)?s?\b|مليون", text):
        multiplier = 1_000_000.0
    elif re.search(r"\bmille\b|\bk\b|الف", text):
        multiplier = 1_000.0
    match = re.search(r"(?<!\d)(\d[\d\s\u00a0.,]*\d|\d)", raw)
    if not match:
        return None, "unparseable_price"
    token = re.sub(r"[\s\u00a0]", "", match.group(1)).strip(".,")
    if multiplier > 1 and re.fullmatch(r"\d+[.,]\d+", token):
        token = token.replace(",", ".")
    else:
        # Portal totals generally use dots/commas as thousands separators.
        token = token.replace(",", "").replace(".", "")
    try:
        amount = float(token) * multiplier
    except ValueError:
        return None, "unparseable_price"
    if amount <= 0 or amount >= 10_000_000_000:
        return None, "price_outside_parser_bounds"
    return (int(amount) if amount.is_integer() else amount), None


def _iso(value: str) -> str | None:
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %m %Y"):
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def parse_publication_date(
    value: Any,
    scraped_at: Any,
    *,
    is_updated: bool = False,
) -> tuple[str | None, str]:
    """Return an observed/derived date and one of the requested status values."""
    raw = clean_text(value)
    if not raw:
        return None, "unavailable"
    exact = _iso(raw)
    if exact:
        return exact, "updated_date" if is_updated else "exact"
    text = normalized(raw)
    anchor_raw = clean_text(scraped_at)
    anchor_iso = _iso(anchor_raw) if anchor_raw else None
    if not anchor_iso:
        return None, "unavailable"
    anchor = datetime.fromisoformat(anchor_iso)
    if re.search(r"aujourd hui|today|اليوم", text):
        delta = timedelta(0)
    elif re.search(r"hier|yesterday|امس", text):
        delta = timedelta(days=1)
    else:
        match = re.search(r"(?:il y a|ago)?\s*(\d+)\s*(minute|heure|hour|jour|day|semaine|week|mois|month)", text)
        if not match:
            return None, "unavailable"
        count = int(match.group(1))
        unit = match.group(2)
        if unit.startswith(("minute",)):
            delta = timedelta(minutes=count)
        elif unit.startswith(("heure", "hour")):
            delta = timedelta(hours=count)
        elif unit.startswith(("jour", "day")):
            delta = timedelta(days=count)
        elif unit.startswith(("semaine", "week")):
            delta = timedelta(weeks=count)
        else:
            delta = timedelta(days=30 * count)
    return (anchor - delta).isoformat(), "relative_parsed"


def tri_state(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    value = normalized(value)
    if value in {"yes", "oui", "true", "1", "present", "avec", "meuble", "furnished"}:
        return "yes"
    if value in {"no", "non", "false", "0", "absent", "sans", "non meuble", "unfurnished"}:
        return "no"
    return "unknown"


def make_listing_id(source: Any, source_id: Any, url: Any, fingerprint_parts: list[Any]) -> str:
    source_key = normalized(source) or "unknown-source"
    native = clean_text(source_id)
    if native:
        return f"{source_key}:native:{native}"
    url_value = canonical_url(url)
    material = url_value or "|".join(normalized(part) for part in fingerprint_parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    strategy = "url" if url_value else "content"
    return f"{source_key}:{strategy}:{digest}"


def empty_record() -> dict[str, Any]:
    record = {column: None for column in V3_COLUMNS}
    for field in AMENITY_COLUMNS:
        record[field] = "unknown"
    record["furnished_status"] = "unknown"
    record["publication_date_status"] = "unavailable"
    record["validation_status"] = "unvalidated"
    record["validation_reasons"] = ""
    record["deduplication_status"] = "unique"
    return record
