"""Deterministic Schema V2 parsing and validation for property listings."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCHEMA_V2_COLUMNS = [
    "listing_id", "listing_id_strategy", "source", "url", "scraped_at", "listing_date",
    "transaction_type", "transaction_parse_reason", "currency", "raw_price_text", "price",
    "price_parse_status", "price_parse_reason", "city", "quartier", "address_text", "latitude",
    "longitude", "location_parse_status", "property_type", "property_type_parse_status",
    "surface_total_m2", "surface_built_m2", "surface_land_m2", "surface_parse_status",
    "surface_parse_reason", "rooms", "bedrooms", "bathrooms", "floor", "total_floors",
    "construction_year", "condition", "new_construction", "renovated", "elevator", "parking",
    "garage", "terrace", "balcony", "garden", "pool", "furnished", "security", "concierge",
    "air_conditioning", "heating", "fireplace", "equipped_kitchen", "double_glazing", "sea_view",
    "mountain_view", "title_deed", "proximity_text", "validation_status", "validation_reasons",
    "title_raw", "location_raw", "details_raw",
]

CITY_ALIASES = {
    "agadir": "Agadir", "casablanca": "Casablanca", "casa": "Casablanca",
    "dar el beida": "Casablanca", "fes": "Fès", "fez": "Fès", "kenitra": "Kénitra",
    "laayoune": "Laâyoune", "marrakech": "Marrakech", "marrakesh": "Marrakech",
    "meknes": "Meknes", "mohammedia": "Mohammedia", "oujda": "Oujda", "rabat": "Rabat",
    "sale": "Salé", "tanger": "Tanger", "tangier": "Tanger", "tetouan": "Tétouan",
    "temara": "Temara", "essaouira": "Essaouira", "el jadida": "El Jadida",
}

PROPERTY_PATTERNS = [
    ("studio", r"\bstudio\b"), ("triplex", r"\btriplex\b"),
    ("duplex", r"\bduplex(?:e)?\b"), ("villa", r"\bvilla\b"),
    ("maison", r"\bmaison\b"), ("appartement", r"\bappartement(?:s)?\b|\bappart\b"),
]

AMENITY_PATTERNS = {
    "elevator": (r"\bascenseur\b|\blift\b|مصعد", r"sans ascenseur|pas d[' ]ascenseur"),
    "parking": (r"\bparking\b|place de voiture", r"sans parking|pas de parking"),
    "garage": (r"\bgarage\b|مراب", r"sans garage|pas de garage"),
    "terrace": (r"\bterrasse\b|rooftop|roof top", r"sans terrasse"),
    "balcony": (r"\bbalcon\b|شرفة", r"sans balcon"),
    "garden": (r"\bjardin\b|rez de jardin|حديقة", r"sans jardin"),
    "pool": (r"\bpiscine\b|مسبح", r"sans piscine"),
    "furnished": (r"\bmeubl[ée]\b|furnished|مفروش", r"non meuble|sans meubles?|vendu vide"),
    "security": (r"securis|securite|surveillance", r"sans securite"),
    "concierge": (r"\bconcierge\b|\bgardien\b", r"sans concierge|sans gardien"),
    "air_conditioning": (r"climatis|air conditionne", r"sans climatisation"),
    "heating": (r"\bchauffage\b", r"sans chauffage"),
    "fireplace": (r"\bcheminee\b", r"sans cheminee"),
    "equipped_kitchen": (r"cuisine equipee", r"cuisine non equipee"),
    "double_glazing": (r"double vitrage", r"sans double vitrage"),
    "sea_view": (r"vue (?:sur )?mer|front de mer|bord de mer", r"sans vue mer"),
    "mountain_view": (r"vue (?:sur )?(?:montagne|atlas)", r"sans vue montagne"),
    "title_deed": (r"titre foncier|titre individuel|melkia", r"sans titre|non titre"),
}


def normalize_for_matching(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def clean_raw_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return None
    query = [(key, value) for key, value in parse_qsl(parts.query) if not key.lower().startswith("utm_")]
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def make_listing_id(source: str, native_id: str | None = None, url: str | None = None,
                    title: str | None = None, location: str | None = None,
                    surface_m2: float | None = None, property_type: str | None = None) -> tuple[str, str]:
    source_key = normalize_for_matching(source) or "unknown-source"
    if native_id and str(native_id).strip():
        return f"{source_key}:native:{str(native_id).strip()}", "native_id"
    canonical_url = canonicalize_url(url)
    if canonical_url:
        digest = hashlib.sha256(f"{source_key}|{canonical_url}".encode()).hexdigest()[:24]
        return f"{source_key}:url:{digest}", "canonical_url"
    fingerprint = "|".join([source_key, normalize_for_matching(title), normalize_for_matching(location),
                            "" if surface_m2 is None else f"{surface_m2:.2f}", normalize_for_matching(property_type)])
    return f"{source_key}:fingerprint:{hashlib.sha256(fingerprint.encode()).hexdigest()[:24]}", "content_fingerprint"


def classify_transaction(source_category: str | None = None, url: str | None = None,
                         title: str | None = None, details: str | None = None) -> dict[str, str]:
    text = normalize_for_matching(" ".join(filter(None, [source_category, url, title, details])))
    sale = bool(re.search(r"a vendre|vente|achat|acheter|for sale|a-vendre", text))
    rent = bool(re.search(r"a louer|location|louer|rent|mensuel|par mois|a-louer", text))
    if sale and rent:
        return {"transaction_type": "UNKNOWN", "transaction_parse_reason": "conflicting_sale_rent_signals"}
    if rent:
        return {"transaction_type": "RENT", "transaction_parse_reason": "explicit_rent_signal"}
    if sale:
        return {"transaction_type": "SALE", "transaction_parse_reason": "explicit_sale_signal"}
    return {"transaction_type": "UNKNOWN", "transaction_parse_reason": "no_reliable_transaction_signal"}


def _parse_number(token: str) -> float | None:
    compact = re.sub(r"\s+", "", token.replace("\u00a0", " ").replace("\u202f", " "))
    if not compact:
        return None
    separators = compact.count(",") + compact.count(".")
    if separators == 1 and re.search(r"[,.]\d{1,2}$", compact):
        compact = compact.replace(",", ".")
    else:
        compact = compact.replace(",", "").replace(".", "")
    try:
        return float(compact)
    except ValueError:
        return None


def parse_price(raw_price_text: str | None, transaction_type: str = "UNKNOWN") -> dict[str, Any]:
    text = normalize_for_matching(clean_raw_text(raw_price_text))
    result = {"currency": None, "price": None, "price_parse_status": "INVALID", "price_parse_reason": "missing_price"}
    if not text:
        return result
    if re.search(r"consulter|sur demande|nous contacter|contactez|projet", text):
        result.update(price_parse_status="MISSING", price_parse_reason="price_on_request"); return result
    result["currency"] = "EUR" if re.search(r"\beur\b|€|euro", text) else "MAD" if re.search(r"\bmad\b|\bdhs?\b|dirham", text) else None
    if re.search(r"/\s*m[²2]|par\s*m[²2]|m[²2]\s*$", text):
        result.update(price_parse_status="WARNING", price_parse_reason="price_per_m2_not_total"); return result
    match = re.search(r"(\d[\d\s\u00a0\u202f.,]*)", text)
    value = _parse_number(match.group(1)) if match else None
    if value is None:
        result["price_parse_reason"] = "no_numeric_value"; return result
    if re.search(r"\b(?:million|millions|mio)\b|\b\d[\d,.]*\s*m\s*(?:dh|mad|eur|€)", text):
        value *= 1_000_000
    elif re.search(r"\b(?:mille|k)\b", text):
        value *= 1_000
    if value <= 0:
        result["price_parse_reason"] = "non_positive_price"; return result
    monthly = bool(re.search(r"mensuel|par mois|/mois", text)) or transaction_type == "RENT"
    if result["currency"] is None:
        result.update(price=value, price_parse_status="WARNING", price_parse_reason="currency_unknown")
    elif monthly:
        result.update(price=value, price_parse_status="WARNING", price_parse_reason="monthly_rent_price")
    else:
        result.update(price=value, price_parse_status="PARSED", price_parse_reason="ok")
    return result


def parse_surfaces(*texts: str | None) -> dict[str, Any]:
    text = normalize_for_matching(" ".join(filter(None, texts)))
    result = {"surface_total_m2": None, "surface_built_m2": None, "surface_land_m2": None,
              "surface_parse_status": "MISSING", "surface_parse_reason": "no_surface"}
    if not text:
        return result
    number = r"(\d+(?:[.,]\d+)?)"
    patterns = {
        "surface_land_m2": [rf"(?:terrain|parcelle|lot)\s*(?:de|:)?\s*{number}\s*m[²2]", rf"{number}\s*m[²2]\s*(?:de\s*)?(?:terrain|parcelle)"],
        "surface_built_m2": [rf"(?:surface\s*)?(?:habitable|construite|batie|built)\s*(?:de|:)?\s*{number}\s*m[²2]", rf"{number}\s*m[²2]\s*(?:habitable|construite|batie)"],
        "surface_total_m2": [rf"(?:surface\s*totale|superficie|surface)\s*(?:de|:)?\s*{number}\s*m[²2]"],
    }
    spans: set[tuple[int, int]] = set()
    for field, candidates in patterns.items():
        for pattern in candidates:
            if match := re.search(pattern, text):
                result[field] = float(match.group(1).replace(",", ".")); spans.add(match.span()); break
    generic = [(match, float(match.group(1).replace(",", "."))) for match in re.finditer(rf"{number}\s*m[²2]", text)]
    unmatched = [value for match, value in generic if not any(start <= match.start() and match.end() <= end for start, end in spans)]
    if result["surface_total_m2"] is None and len(unmatched) == 1:
        result["surface_total_m2"] = unmatched[0]
    values = [result[key] for key in ("surface_total_m2", "surface_built_m2", "surface_land_m2") if result[key] is not None]
    if values:
        result.update(surface_parse_status="WARNING" if len(unmatched) > 1 else "PARSED",
                      surface_parse_reason="ambiguous_unlabeled_surfaces" if len(unmatched) > 1 else "multiple_surface_types" if len(values) > 1 else "ok")
    elif generic:
        result.update(surface_parse_status="WARNING", surface_parse_reason="ambiguous_unlabeled_surfaces")
    return result


def parse_location(location_raw: str | None) -> dict[str, Any]:
    raw = clean_raw_text(location_raw)
    if not raw:
        return {"city": None, "quartier": None, "address_text": None, "location_parse_status": "MISSING"}
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    if len(parts) >= 2:
        return {"city": CITY_ALIASES.get(normalize_for_matching(parts[-1]), parts[-1]), "quartier": ", ".join(parts[:-1]),
                "address_text": raw, "location_parse_status": "PARSED"}
    key = normalize_for_matching(raw)
    if key in CITY_ALIASES:
        return {"city": CITY_ALIASES[key], "quartier": None, "address_text": raw, "location_parse_status": "CITY_ONLY"}
    return {"city": None, "quartier": None, "address_text": raw, "location_parse_status": "AMBIGUOUS"}


def extract_property_type(*texts: str | None) -> dict[str, str | None]:
    text = normalize_for_matching(" ".join(filter(None, texts)))
    matches = [name for name, pattern in PROPERTY_PATTERNS if re.search(pattern, text)]
    if len(matches) == 1:
        return {"property_type": matches[0], "property_type_parse_status": "PARSED"}
    return {"property_type": None, "property_type_parse_status": "AMBIGUOUS" if matches else "MISSING"}


def extract_amenities(*texts: str | None) -> dict[str, bool | None]:
    text = normalize_for_matching(" ".join(filter(None, texts)))
    output = {}
    for field, (positive, negative) in AMENITY_PATTERNS.items():
        output[field] = False if re.search(negative, text) else True if re.search(positive, text) else None
    return output


def parse_rooms(*texts: str | None) -> dict[str, int | None]:
    text = normalize_for_matching(" ".join(filter(None, texts)))
    patterns = {"rooms": r"(\d+)\s*pieces?", "bedrooms": r"(\d+)\s*(?:chambres?|ch\.)",
                "bathrooms": r"(\d+)\s*(?:salles? de bains?|sdb)",
                "total_floors": r"(?:immeuble de|total)\s*(\d+)\s*etages?",
                "construction_year": r"(?:construit en|annee de construction)\s*(19\d{2}|20\d{2})"}
    values = {field: int(match.group(1)) if (match := re.search(pattern, text)) else None for field, pattern in patterns.items()}
    floor = re.search(r"(?:au|du|de)\s*(\d{1,2})(?:er|e|eme)?\s*etage", text)
    values["floor"] = 0 if re.search(r"\brdc\b|rez[ -]de[ -]chaussee", text) else int(floor.group(1)) if floor else None
    return values


def parse_condition(*texts: str | None) -> dict[str, Any]:
    text = normalize_for_matching(" ".join(filter(None, texts)))
    new = bool(re.search(r"\bneuf\b|nouvelle construction|premiere main|jamais habite|en construction", text))
    renovated = bool(re.search(r"renove|refait a neuf", text))
    condition = "TO_RENOVATE" if re.search(r"a renover|travaux a prevoir", text) else "RENOVATED" if renovated else "NEW" if new else None
    return {"condition": condition, "new_construction": True if new else None, "renovated": True if renovated else None}


def extract_proximity_text(*texts: str | None) -> str | None:
    text = normalize_for_matching(" ".join(filter(None, texts)))
    phrases = re.findall(r"(?:proche de|a proximite de|a \d+ minutes? de|pres de)[^.;,]{0,80}", text)
    return " | ".join(phrases) if phrases else None


def validate_listing(record: dict[str, Any]) -> dict[str, str]:
    invalid, warnings = [], []
    if not record.get("listing_id"): invalid.append("missing_listing_id")
    if record.get("transaction_type") == "UNKNOWN": warnings.append("unknown_transaction")
    if record.get("transaction_type") == "SALE" and record.get("price") is None: invalid.append("sale_price_missing")
    if record.get("price_parse_status") == "WARNING": warnings.append("price_parse_warning")
    if record.get("surface_parse_status") == "WARNING": warnings.append("surface_parse_warning")
    if record.get("property_type") is None: warnings.append("property_type_missing_or_ambiguous")
    price = record.get("price")
    if price is not None:
        if price <= 0: invalid.append("price_non_positive")
        elif price < 20_000 or price > 200_000_000: warnings.append("price_extreme")
    surfaces = [record.get(name) for name in ("surface_total_m2", "surface_built_m2", "surface_land_m2")]
    known = [value for value in surfaces if value is not None]
    if not known: warnings.append("surface_missing")
    elif any(value <= 0 for value in known): invalid.append("surface_non_positive")
    elif any(value > 20_000 for value in known): warnings.append("surface_extreme")
    for field in ("rooms", "bedrooms", "bathrooms"):
        if record.get(field) is not None and record[field] < 0: invalid.append(f"{field}_negative")
    if record.get("rooms") is not None and record.get("bedrooms") is not None and record["rooms"] < record["bedrooms"]:
        warnings.append("rooms_below_bedrooms")
    if record.get("floor") is not None and record.get("total_floors") is not None and record["floor"] > record["total_floors"]:
        warnings.append("floor_above_total_floors")
    year = record.get("construction_year")
    if year is not None and not 1800 <= year <= datetime.now().year + 1:
        warnings.append("construction_year_suspicious")
    if not record.get("city"): warnings.append("missing_city")
    if record.get("latitude") is not None and not -90 <= record["latitude"] <= 90:
        invalid.append("latitude_invalid")
    if record.get("longitude") is not None and not -180 <= record["longitude"] <= 180:
        invalid.append("longitude_invalid")
    reasons = list(dict.fromkeys(invalid + warnings))
    return {"validation_status": "INVALID" if invalid else "WARNING" if warnings else "VALID",
            "validation_reasons": "|".join(reasons)}


def build_v2_record(raw: dict[str, Any], source: str = "mubawab.ma") -> dict[str, Any]:
    title = clean_raw_text(raw.get("title_raw") or raw.get("title"))
    location_raw = clean_raw_text(raw.get("location_raw") or raw.get("location"))
    details = clean_raw_text(raw.get("details_raw") or raw.get("details"))
    url = canonicalize_url(raw.get("url"))
    transaction = classify_transaction(raw.get("source_category"), url, title, details)
    price = parse_price(raw.get("raw_price_text") or raw.get("price_text"), transaction["transaction_type"])
    location = parse_location(location_raw)
    property_result = extract_property_type(title, details)
    if property_result["property_type"] is None:
        property_result = extract_property_type(raw.get("source_category"), url)
    surfaces, rooms = parse_surfaces(title, details), parse_rooms(title, details)
    listing_id, strategy = make_listing_id(source, raw.get("native_id"), url, title, location_raw,
                                           surfaces.get("surface_total_m2"), property_result.get("property_type"))
    record = {column: None for column in SCHEMA_V2_COLUMNS}
    record.update({"listing_id": listing_id, "listing_id_strategy": strategy, "source": source, "url": url,
                   "scraped_at": raw.get("scraped_at") or datetime.now(timezone.utc).isoformat(),
                   "listing_date": raw.get("listing_date"), "raw_price_text": clean_raw_text(raw.get("raw_price_text") or raw.get("price_text")),
                   "latitude": raw.get("latitude"), "longitude": raw.get("longitude"), "title_raw": title,
                   "location_raw": location_raw, "details_raw": details,
                   "proximity_text": extract_proximity_text(title, details)})
    for parsed in (transaction, price, location, property_result, surfaces, rooms, parse_condition(title, details), extract_amenities(title, details)):
        record.update(parsed)
    record.update(validate_listing(record))
    return {column: record.get(column) for column in SCHEMA_V2_COLUMNS}
