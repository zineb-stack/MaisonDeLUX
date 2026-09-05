"""Quality metrics, acceptance checks, and human-readable reports."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .geography import valid_neighborhood
from .schema import V3_COLUMNS


MISSING_FIELDS = [
    "publication_date", "url", "source_listing_id", "city", "region", "neighborhood",
    "property_type", "surface_m2", "price_mad", "bedrooms", "bathrooms",
    "latitude", "longitude",
]
EXACT_DUPLICATE_PREFIXES = ("duplicate_listing_id", "duplicate_source_id", "duplicate_url", "duplicate_fingerprint")


def _missing_percent(frame: pd.DataFrame, column: str) -> float:
    if frame.empty:
        return 100.0
    values = frame[column] if column in frame else pd.Series([None] * len(frame))
    return round(float(values.isna().mean() * 100), 2)


def _counts(frame: pd.DataFrame, column: str, limit: int | None = None) -> dict[str, int]:
    if frame.empty or column not in frame:
        return {}
    counts = frame[column].fillna("<null>").astype(str).value_counts()
    if limit:
        counts = counts.head(limit)
    return {str(key): int(value) for key, value in counts.items()}


def build_report(raw_count: int, rows: list[dict[str, Any]], source_statuses: dict[str, str], mode: str) -> dict[str, Any]:
    frame = pd.DataFrame(rows, columns=V3_COLUMNS)
    exact_duplicate = frame["deduplication_status"].fillna("").str.startswith(EXACT_DUPLICATE_PREFIXES) if not frame.empty else pd.Series(dtype=bool)
    clean = frame[(~exact_duplicate) & frame["validation_status"].isin(["valid", "warning"])] if not frame.empty else frame
    rejected = frame[frame["validation_status"] == "rejected"] if not frame.empty else frame
    city_counts = clean["city"].value_counts() if not clean.empty else pd.Series(dtype=int)
    max_city_share = float(city_counts.iloc[0] / len(clean)) if len(clean) else 0.0
    invalid_neighborhoods = int(sum(
        value is not None and not valid_neighborhood(value, city)
        for value, city in zip(clean.get("neighborhood", []), clean.get("city", []))
    ))
    duplicate_listing_ids = int(clean["listing_id"].duplicated().sum()) if not clean.empty else 0
    source_count = int(clean["source"].nunique(dropna=True)) if not clean.empty else 0
    region_count = int(clean["region"].nunique(dropna=True)) if not clean.empty else 0
    property_count = int(clean["property_type"].nunique(dropna=True)) if not clean.empty else 0
    publication_available = int(clean["publication_date"].notna().sum()) if not clean.empty else 0
    source_present = clean["source"].notna() & clean["source"].astype(str).str.strip().ne("") if not clean.empty else pd.Series(dtype=bool)
    identifier_present = (
        (clean["url"].notna() & clean["url"].astype(str).str.strip().ne(""))
        | (clean["source_listing_id"].notna() & clean["source_listing_id"].astype(str).str.strip().ne(""))
    ) if not clean.empty else pd.Series(dtype=bool)
    traceable = source_present & identifier_present if not clean.empty else pd.Series(dtype=bool)
    traceability_rate = float(traceable.mean()) if len(clean) else 0.0
    field_availability_by_property_type: dict[str, dict[str, Any]] = {}
    if not clean.empty:
        for property_type, group in clean.groupby("property_type", dropna=False):
            field_availability_by_property_type[str(property_type)] = {
                "rows": int(len(group)),
                "bedrooms_available_percent": round(float(group["bedrooms"].notna().mean() * 100), 2),
                "bathrooms_available_percent": round(float(group["bathrooms"].notna().mean() * 100), 2),
            }
    publication_by_source: dict[str, dict[str, Any]] = {}
    if not clean.empty:
        for source, group in clean.groupby("source", dropna=False):
            available = int(group["publication_date"].notna().sum())
            publication_by_source[str(source)] = {
                "rows": int(len(group)),
                "available": available,
                "available_percent": round(100 * available / len(group), 2),
                "status_counts": _counts(group, "publication_date_status"),
            }

    source_row_counts = frame["source"].value_counts(dropna=True) if not frame.empty else pd.Series(dtype=int)
    checks = {
        "A_unique_listing_id": duplicate_listing_ids == 0,
        "B_sale_only": bool(len(clean)) and bool((clean["transaction_type"] == "sale").all()),
        "C_price_available_99_percent": bool(len(clean)) and float(clean["price_mad"].notna().mean()) >= 0.99,
        "D_surface_available_90_percent": bool(len(clean)) and float(clean["surface_m2"].notna().mean()) >= 0.90,
        "E_city_available_99_percent": bool(len(clean)) and float(clean["city"].notna().mean()) >= 0.99,
        "F_region_available_99_percent": bool(len(clean)) and float(clean["region"].notna().mean()) >= 0.99,
        "G_property_type_resolved_99_percent": bool(len(clean)) and float(
            (clean["property_type"].notna() & clean["property_type"].ne("other")).mean()
        ) >= 0.99,
        "I_neighborhood_no_fragments": invalid_neighborhoods == 0,
        "J_city_balanced": max_city_share <= 0.35,
        "K_several_property_types": property_count >= 3,
        "L_several_regions": region_count >= 6,
        "M_traceability_90_percent": bool(len(clean)) and traceability_rate >= 0.90,
        "pilot_at_least_one_source": source_count >= 1,
        "pilot_size_100_to_300_per_source": (
            bool(len(source_row_counts)) and bool(source_row_counts.between(100, 300).all())
        ) if mode == "PILOT" else True,
        "checkpoint_resume_tested": False,
    }
    publication_statuses = set(clean["publication_date_status"].dropna().astype(str)) if not clean.empty else set()
    allowed_publication_statuses = {"exact", "relative_parsed", "updated_date", "unavailable"}
    unavailable_is_null = bool((
        clean.loc[clean["publication_date_status"] == "unavailable", "publication_date"].isna().all()
    )) if not clean.empty else True
    missing_date_is_unavailable = bool((
        clean.loc[clean["publication_date"].isna(), "publication_date_status"].eq("unavailable").all()
    )) if not clean.empty else True
    information = {
        "publication_date_available_percent": round(100 * publication_available / len(clean), 2) if len(clean) else 0.0,
        "publication_date_is_non_blocking": True,
        "publication_date_statuses_are_honest": (
            publication_statuses.issubset(allowed_publication_statuses)
            and unavailable_is_null
            and missing_date_is_unavailable
        ),
        "coordinates_available_percent": round(float((clean["latitude"].notna() & clean["longitude"].notna()).mean() * 100), 2) if len(clean) else 0.0,
        "traceability_percent": round(traceability_rate * 100, 2),
        "single_source_is_acceptable": True,
    }
    report = {
        "mode": mode,
        "summary": {
            "total_raw_listings": int(raw_count),
            "total_normalized": int(len(frame)),
            "total_valid": int((frame["validation_status"] == "valid").sum()) if not frame.empty else 0,
            "total_warnings": int((frame["validation_status"] == "warning").sum()) if not frame.empty else 0,
            "total_rejected": int(len(rejected)),
            "total_duplicates": int(exact_duplicate.sum()) if not frame.empty else 0,
            "total_modeling_rows": int(len(clean)),
            "number_of_sources": source_count,
            "number_of_regions": region_count,
            "number_of_cities": int(clean["city"].nunique(dropna=True)) if not clean.empty else 0,
            "number_of_neighborhoods": int(clean["neighborhood"].nunique(dropna=True)) if not clean.empty else 0,
            "median_price_mad": float(clean["price_mad"].median()) if len(clean) else None,
            "median_surface_m2": float(clean["surface_m2"].median()) if len(clean) else None,
            "median_price_per_m2": float(clean["price_per_m2"].median()) if len(clean) else None,
            "largest_city_share_percent": round(max_city_share * 100, 2),
        },
        "missing_percent": {field: _missing_percent(clean, field) for field in MISSING_FIELDS},
        "distributions": {
            "source": _counts(clean, "source"),
            "region": _counts(clean, "region"),
            "city": _counts(clean, "city", 50),
            "property_type": _counts(clean, "property_type"),
            "publication_date_status": _counts(clean, "publication_date_status"),
            "validation_status": _counts(frame, "validation_status"),
            "deduplication_status": _counts(frame, "deduplication_status"),
        },
        "source_statuses": source_statuses,
        "publication_date_by_source": publication_by_source,
        "field_availability_by_property_type": field_availability_by_property_type,
        "acceptance_checks": checks,
        "informational_checks": information,
        "pilot_passed": all(checks.values()) if mode == "PILOT" else None,
    }
    return report


def write_report(report: dict[str, Any], report_dir: Path, stem: str) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{stem}.json"
    md_path = report_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = report["summary"]
    lines = [
        f"# MaisonDeLUX V3 {report['mode']} quality report", "",
        "## Summary", "",
        "| Metric | Value |", "|---|---:|",
        *[f"| {key.replace('_', ' ')} | {value if value is not None else 'null'} |" for key, value in summary.items()],
        "", "## Missing values", "", "| Field | Missing % |", "|---|---:|",
        *[f"| {key} | {value:.2f} |" for key, value in report["missing_percent"].items()],
        "", "## Acceptance checks", "", "| Check | Passed |", "|---|:---:|",
        *[f"| {key} | {'YES' if value else 'NO'} |" for key, value in report["acceptance_checks"].items()],
        "", "## Informational metrics (non-blocking)", "", "| Metric | Value |", "|---|---:|",
        *[f"| {key} | {value} |" for key, value in report["informational_checks"].items()],
        "", "## Source status", "", "| Adapter | Status |", "|---|---|",
        *[f"| {key} | {value} |" for key, value in report["source_statuses"].items()],
        "", "## Publication date by source", "", "| Source | Rows | Available | Available % |", "|---|---:|---:|---:|",
        *[
            f"| {source} | {values['rows']} | {values['available']} | {values['available_percent']:.2f} |"
            for source, values in report["publication_date_by_source"].items()
        ],
        "", "## Bedrooms and bathrooms by property type", "", "| Property type | Rows | Bedrooms available % | Bathrooms available % |", "|---|---:|---:|---:|",
        *[
            f"| {property_type} | {values['rows']} | {values['bedrooms_available_percent']:.2f} | {values['bathrooms_available_percent']:.2f} |"
            for property_type, values in report["field_availability_by_property_type"].items()
        ],
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
