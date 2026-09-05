"""Normalize raw source evidence into the MaisonDeLUX V3 schema."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .geography import parse_location
from .schema import (
    AMENITY_COLUMNS,
    V3_COLUMNS,
    canonical_url,
    clean_text,
    empty_record,
    make_listing_id,
    missing,
    normalized,
    parse_price_mad,
    parse_publication_date,
    safe_float,
    safe_int,
    tri_state,
)


TYPE_PATTERNS: list[tuple[str, str]] = [
    ("local commercial", r"\blocal(?:e)? commercial(?:e)?\b|commercial premises|(?:^|vente de |a vendre )commerce\b|محل تجاري"),
    ("magasin", r"\bmagasin\b|\bboutique\b|\bshop\b|متجر"),
    ("immeuble", r"\bimmeuble\b|\bbatiment\b|\bbuilding\b|عمارة"),
    ("terrain", r"\bterrain\b|\blot de terrain\b|\bparcelle\b|\bland(?: for sale)?\b|ارض"),
    ("bureau", r"\bbureau(?:x)?\b|\boffice\b|مكتب"),
    ("villa", r"\bvilla\b|فيلا"),
    ("maison", r"\bmaison(?=\b|\d)|\bhouse\b|منزل"),
    ("studio", r"\bstudio\b"),
    ("duplex", r"\b(?:duplexe?|dublex)\b"),
    ("riad", r"(?<!hay )\briad\b(?! (?:agdal|salam|andalous))"),
    ("appartement", r"\bappartement(?:s)?\b|\bappart\b|\bappt\b|\bapprt\b|\bapartment\b|شقة"),
]

AMENITY_PATTERNS = {
    "parking": (r"\bparking\b|place de voiture", r"sans parking|pas de parking"),
    "balcony": (r"\bbalcon\b|شرفة", r"sans balcon|pas de balcon"),
    "terrace": (r"\bterrasse\b|rooftop", r"sans terrasse|pas de terrasse"),
    "garden": (r"\bjardin\b|حديقة", r"sans jardin|pas de jardin"),
    "pool": (r"\bpiscine\b|مسبح", r"sans piscine|pas de piscine"),
    "elevator": (r"\bascenseur\b|\blift\b|مصعد", r"sans ascenseur|pas d ascenseur"),
    "garage": (r"\bgarage\b|مراب", r"sans garage|pas de garage"),
    "security": (r"securis|securite|surveillance|gardien", r"sans securite|non securise"),
    "air_conditioning": (r"climatis|air conditionne", r"sans climatisation"),
    "sea_view": (r"vue (?:sur )?mer|front de mer|bord de mer", r"sans vue mer"),
}


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if not missing(value):
            return value
    return None


def _extract_number(text: Any, labels: str) -> int | None:
    value = normalized(text)
    match = re.search(rf"(?:{labels})\s*[:\-]?\s*(\d{{1,3}})|(?<!\d)(\d{{1,3}})\s*(?:{labels})", value)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _surface_from_text(text: Any) -> float | None:
    value = normalized(text)
    match = re.search(r"(?<!\d)(\d{1,6}(?:[.,]\d+)?)\s*m(?:2|²)\b", value)
    return float(match.group(1).replace(",", ".")) if match else None


def infer_property_type(record: dict[str, Any]) -> tuple[str, list[str]]:
    explicit = normalized(_first(record, "source_category", "category", "property_type"))
    title = normalized(_first(record, "title_raw", "title"))
    description = normalized(_first(record, "description_raw", "description", "details_raw"))
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for property_type, pattern in TYPE_PATTERNS:
        for label, text, weight in (("title", title, 5), ("category", explicit, 4), ("description", description, 1)):
            if text and re.search(pattern, text):
                scores[property_type] = scores.get(property_type, 0) + weight
                evidence.setdefault(property_type, []).append(label)
    if not scores:
        return "other", ["property_type_unresolved"]
    order = {name: len(TYPE_PATTERNS) - index for index, (name, _) in enumerate(TYPE_PATTERNS)}
    explicit_type = next((name for name, pattern in TYPE_PATTERNS if explicit and re.search(pattern, explicit)), None)
    title_matches: list[tuple[int, int, str, re.Match[str]]] = []
    for property_type, pattern in TYPE_PATTERNS:
        match = re.search(pattern, title) if title else None
        if match:
            title_matches.append((match.start(), -order[property_type], property_type, match))
    title_matches.sort(key=lambda item: (item[0], item[1]))

    if title_matches:
        _, _, title_type, title_match = title_matches[0]
        # Studio and duplex are apartment subtypes; an early explicit subtype
        # is more informative than a generic leading "appartement".
        subtype_matches = [item for item in title_matches if item[2] in {"studio", "duplex"} and item[0] <= 25]
        if title_type == "appartement" and subtype_matches:
            _, _, title_type, title_match = subtype_matches[0]
        prefix = title[max(0, title_match.start() - 18):title_match.start()]
        suffix = title[title_match.end():title_match.end() + 22]
        strong_title = (
            title_match.start() <= 18
            or bool(re.search(r"vente(?: de| d un| d une)?|vends?|a vendre|for sale", prefix))
            or bool(re.search(r"a vendre|for sale|traditionnel|authentique|titre|a renover|a refaire", suffix))
        )
        if title_type == "riad":
            # Riad is frequently a neighborhood/residence name. Require a
            # property phrase when a source category says apartment.
            strong_title = bool(re.search(
                r"\briad (?:traditionnel|authentique|titre|renove|a renover|a refaire|de charme|a vendre)\b|maison d hotes",
                title,
            ))
        if title_type == "terrain" and title_match.group(0).startswith("land"):
            strong_title = bool(re.search(r"^land\b|\bland for sale\b", title))
        chosen = title_type if (strong_title or not explicit_type) else explicit_type
    elif explicit_type:
        chosen = explicit_type
    else:
        chosen = max(scores, key=lambda name: (scores[name], order[name]))
    reasons: list[str] = []
    if explicit_type and chosen != explicit_type and "title" in evidence.get(chosen, []):
        reasons.append(f"property_type_contradiction:{explicit_type}->{chosen}")
    return chosen, reasons


def infer_transaction(record: dict[str, Any]) -> tuple[str, list[str]]:
    explicit = normalized(_first(record, "transaction_type", "transaction", "deal_type"))
    text = normalized(" ".join(filter(None, [
        clean_text(_first(record, "source_category", "category")),
        clean_text(_first(record, "title_raw", "title")),
        clean_text(_first(record, "description_raw", "description")),
        clean_text(record.get("url")),
    ])))
    sale = explicit in {"sale", "vente", "acheter", "a vendre", "for sale", "للبيع"} or bool(re.search(r"\ba vendre\b|\bvente\b|\bachat\b|\bach[eè]ter\b|for sale|للبيع", text))
    rent = explicit in {"rent", "rental", "location", "louer", "a louer", "للايجار", "للإيجار"} or bool(re.search(r"\ba louer\b|\blocation\b|\bloyer\b|par mois|mensuel|for rent|للايجار|للإيجار", text))
    if sale and not rent:
        return "sale", []
    if rent and not sale:
        return "rent", []
    return "unknown", ["transaction_conflict" if sale and rent else "transaction_unresolved"]


def normalize_record(raw: dict[str, Any], source_record_path: str | None = None) -> dict[str, Any]:
    record = empty_record()
    reasons: list[str] = []
    source = clean_text(_first(raw, "source", "source_name")) or "unknown"
    url = canonical_url(_first(raw, "url", "canonical_url", "listing_url"))
    native_id = clean_text(_first(raw, "source_listing_id", "native_id", "id", "reference"))
    if not native_id and url:
        match = re.search(r"/(?:a|pa|annonce|property|listing)/?(\d{4,})", url, re.I)
        if match:
            native_id = match.group(1)

    scraped_at = clean_text(_first(raw, "scraped_at", "collected_at")) or datetime.now(timezone.utc).isoformat()
    publication_raw = _first(raw, "publication_date", "date_published", "datePublished", "published_at", "listing_date")
    updated_raw = _first(raw, "date_modified", "dateModified", "updated_at")
    publication, publication_status = parse_publication_date(publication_raw, scraped_at)
    if not publication and not missing(updated_raw):
        publication, publication_status = parse_publication_date(updated_raw, scraped_at, is_updated=True)

    title = clean_text(_first(raw, "title_raw", "title", "name"))
    description = clean_text(_first(raw, "description_raw", "description", "details_raw", "details"))
    location_raw = clean_text(_first(raw, "location_raw", "location", "address_text", "address"))
    city, neighborhood, region = parse_location(
        _first(raw, "city", "addressLocality"),
        _first(raw, "neighborhood", "quartier", "district"),
        location_raw,
    )

    property_type, type_reasons = infer_property_type(raw)
    transaction_type, transaction_reasons = infer_transaction(raw)
    reasons.extend(type_reasons + transaction_reasons)

    price_raw = clean_text(_first(raw, "price_raw", "raw_price_text", "price_text", "price"))
    numeric_price = safe_float(raw.get("price_mad"))
    if numeric_price is not None and numeric_price > 0:
        price_mad, price_reason = numeric_price, None
    else:
        price_mad, price_reason = parse_price_mad(price_raw, _first(raw, "currency", "price_currency"))
    if price_reason:
        reasons.append(price_reason)

    evidence_text = " ".join(filter(None, [title, description, clean_text(_first(raw, "details_raw", "details"))]))
    surface = safe_float(_first(raw, "surface_m2", "surface_total_m2", "area", "floor_size"))
    if surface is None:
        surface = _surface_from_text(evidence_text)
    land_surface = safe_float(_first(raw, "land_surface_m2", "surface_land_m2", "land_area"))
    built_surface = safe_float(_first(raw, "built_surface_m2", "surface_built_m2", "built_area"))
    bedrooms = safe_int(_first(raw, "bedrooms", "numberOfBedrooms"))
    bathrooms = safe_int(_first(raw, "bathrooms", "numberOfBathroomsTotal"))
    floor = safe_int(_first(raw, "floor", "floor_number"))
    total_floors = safe_int(_first(raw, "total_floors", "number_of_floors"))
    bedrooms = bedrooms if bedrooms is not None else _extract_number(evidence_text, r"chambres?|bedrooms?")
    bathrooms = bathrooms if bathrooms is not None else _extract_number(evidence_text, r"salles? de bains?|bathrooms?")
    # Room counts are not meaningful modeling features for these categories.
    # Null is preferable to a portal/API placeholder such as zero.
    if property_type in {"terrain", "bureau", "local commercial", "magasin"}:
        bedrooms = None
    if property_type == "terrain" or (
        property_type in {"bureau", "local commercial", "magasin"} and bathrooms == 0
    ):
        bathrooms = None

    record.update({
        "source": source, "source_listing_id": native_id, "url": url,
        "scraped_at": scraped_at, "publication_date": publication,
        "publication_date_status": publication_status, "transaction_type": transaction_type,
        "region": region, "city": city, "neighborhood": neighborhood,
        "latitude": safe_float(raw.get("latitude")), "longitude": safe_float(raw.get("longitude")),
        "property_type": property_type, "surface_m2": surface,
        "land_surface_m2": land_surface, "built_surface_m2": built_surface,
        "bedrooms": bedrooms, "bathrooms": bathrooms, "floor": floor,
        "total_floors": total_floors, "price_mad": price_mad, "price_raw": price_raw,
        "price_per_m2": round(price_mad / surface, 2) if price_mad and surface and surface > 0 else None,
        "title_raw": title, "description_raw": description, "location_raw": location_raw,
        "source_record_path": source_record_path or clean_text(raw.get("source_record_path")),
    })

    for field in AMENITY_COLUMNS:
        explicit_value = raw.get(field)
        if not missing(explicit_value):
            record[field] = tri_state(explicit_value)
            continue
        text = normalized(evidence_text)
        positive, negative = AMENITY_PATTERNS[field]
        record[field] = "no" if re.search(negative, text) else "yes" if re.search(positive, text) else "unknown"
    furnished = _first(raw, "furnished_status", "furnished", "meuble")
    if not missing(furnished):
        state = tri_state(furnished)
    else:
        text = normalized(evidence_text)
        state = "no" if re.search(r"non meuble|sans meubles?|vendu vide", text) else "yes" if re.search(r"\bmeuble\b|furnished|مفروش", text) else "unknown"
    record["furnished_status"] = state

    record["listing_id"] = make_listing_id(
        source, native_id, url,
        [city, neighborhood, property_type, surface, bedrooms, price_mad, title],
    )
    record["validation_reasons"] = "|".join(dict.fromkeys(reasons))
    return {column: record.get(column) for column in V3_COLUMNS}
