"""Validation rules for the canonical data product."""
from __future__ import annotations

from typing import Any

from ml.src.data_schema import normalize_for_matching, valid_neighborhood


VALID_PROPERTY_TYPES = {"appartement", "studio", "duplex", "villa", "maison", "terrain", "bureau", "commerce"}


def validate_canonical(row: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = [reason for reason in str(row.get("validation_reasons") or "").split("|") if reason]
    transaction = normalize_for_matching(row.get("transaction_type"))
    if transaction == "rent":
        reasons.append("rental_listing")
    elif transaction != "sale":
        reasons.append("unknown_transaction")
    price = row.get("price_mad")
    surface = row.get("surface_m2")
    if price is None:
        reasons.append("missing_price")
    elif not 50_000 <= float(price) <= 500_000_000:
        reasons.append("implausible_price")
    if surface is None:
        reasons.append("missing_surface")
    elif not 10 <= float(surface) <= 100_000:
        reasons.append("implausible_surface")
    if not row.get("city"):
        reasons.append("missing_city")
    if not valid_neighborhood(row.get("neighborhood")):
        reasons.append("missing_or_invalid_neighborhood")
    if row.get("property_type") not in VALID_PROPERTY_TYPES:
        reasons.append("unknown_property_type")
    for field, maximum in (("bedrooms", 20), ("bathrooms", 15)):
        value = row.get(field)
        if value is not None and not 0 <= float(value) <= maximum:
            reasons.append(f"implausible_{field}")
    latitude, longitude = row.get("latitude"), row.get("longitude")
    if latitude is not None or longitude is not None:
        if latitude is None or longitude is None or not (20.5 <= float(latitude) <= 36.5 and -17.5 <= float(longitude) <= -0.5):
            reasons.append("coordinates_outside_morocco")
    ppm2 = row.get("price_per_m2")
    if ppm2 is not None and row.get("property_type") in {"appartement", "studio", "duplex", "villa", "maison"} and not 1_000 <= float(ppm2) <= 150_000:
        reasons.append("price_per_m2_outlier")
    reasons = list(dict.fromkeys(reasons))
    hard = {
        "rental_listing", "unknown_transaction", "missing_price", "implausible_price",
        "missing_surface", "implausible_surface", "missing_city", "unknown_property_type",
        "coordinates_outside_morocco", "price_per_m2_outlier",
    }
    status = "rejected" if hard.intersection(reasons) else "warning" if reasons else "valid"
    return status, reasons
