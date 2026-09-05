"""End-to-end V3 orchestration used by the single Run-All notebook."""
from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .checkpoints import JsonlCheckpoint
from .normalization import normalize_record
from .reporting import EXACT_DUPLICATE_PREFIXES, build_report, write_report
from .schema import V3_COLUMNS
from .sources import SourceSpec, collect_sources
from .validation import mark_duplicates, validate_rows


PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class PipelineConfig:
    mode: str = "PILOT"
    config_path: Path = PROJECT_ROOT / "config" / "scraping_v3.json"
    project_root: Path = PROJECT_ROOT
    force_pilot_gate: bool = True


@dataclass
class RunResult:
    mode: str
    raw_count: int
    normalized_count: int
    clean_count: int
    pilot_passed: bool | None
    processed_path: Path
    report_json_path: Path
    report_markdown_path: Path
    source_statuses: dict[str, str]
    report: dict[str, Any]


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _traceability_score(row: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(bool(row.get("source_listing_id"))) + int(bool(row.get("url"))),
        int(bool(row.get("publication_date"))),
        int(bool(row.get("neighborhood"))),
    )


def balanced_sample(rows: list[dict[str, Any]], target: int, city_cap: float) -> list[dict[str, Any]]:
    """Round-robin source/region/city/type groups while preferring traceable rows."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(field) or "<null>") for field in ("source", "region", "city", "property_type"))
        groups[key].append(row)
    queues: list[deque[dict[str, Any]]] = []
    for key in sorted(groups):
        group = sorted(groups[key], key=_traceability_score, reverse=True)
        queues.append(deque(group))
    result: list[dict[str, Any]] = []
    city_counts: dict[str, int] = defaultdict(int)
    max_per_city = max(1, int(target * city_cap))
    while queues and len(result) < target:
        next_round: list[deque[dict[str, Any]]] = []
        made_progress = False
        for queue in queues:
            while queue:
                row = queue.popleft()
                city = str(row.get("city") or "<null>")
                if city_counts[city] >= max_per_city:
                    continue
                result.append(row)
                city_counts[city] += 1
                made_progress = True
                break
            if queue:
                next_round.append(queue)
            if len(result) >= target:
                break
        queues = next_round
        if not made_progress:
            break
    return result


def _write_raw_observations(records: list[dict[str, Any]], path: Path) -> int:
    checkpoint = JsonlCheckpoint(path)
    return checkpoint.append_batch(records)


def _checkpoint_resume_self_test(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    first = JsonlCheckpoint(path)
    sample = {"source": "resume-self-test", "source_listing_id": "1", "url": "https://example.invalid/a/1"}
    first.append_batch([sample])
    second = JsonlCheckpoint(path)
    before = second.rows
    appended = second.append_batch([sample])
    return before >= 1 and appended == 0 and second.rows == before


def _execute(config: PipelineConfig, settings: dict[str, Any], mode: str) -> RunResult:
    mode = mode.upper()
    if mode not in {"PILOT", "FAST", "FULL"}:
        raise ValueError("MODE must be PILOT, FAST, or FULL")
    target = int(settings["modes"][mode]["target"])
    city_cap = float(settings["modes"][mode]["max_city_share"])
    specs = [SourceSpec.from_dict(item) for item in settings["sources"]]
    checkpoint_dir = config.project_root / settings["paths"]["checkpoints"]
    raw_records, statuses = collect_sources(specs, config.project_root, checkpoint_dir, mode=mode, target=target)
    if not raw_records:
        raise RuntimeError("No source records were available. Add an authorized feed or enable a documented authorized source.")

    normalized_all = [
        normalize_record(record, record.get("source_record_path"))
        for record in raw_records
    ]
    rows = balanced_sample(normalized_all, min(target, len(normalized_all)), city_cap)
    raw_by_normalized_object = {id(normalized): raw for normalized, raw in zip(normalized_all, raw_records)}
    selected_raw = [raw_by_normalized_object[id(row)] for row in rows]
    mark_duplicates(rows)
    validate_rows(rows)

    raw_path = config.project_root / settings["paths"]["raw"] / f"{mode.casefold()}_observations.jsonl"
    _write_raw_observations(selected_raw, raw_path)
    report = build_report(len(selected_raw), rows, statuses, mode)
    resume_path = checkpoint_dir / "_resume_self_test.jsonl"
    report["acceptance_checks"]["checkpoint_resume_tested"] = _checkpoint_resume_self_test(resume_path)
    if mode == "PILOT":
        report["pilot_passed"] = all(report["acceptance_checks"].values())

    output_dir = config.project_root / settings["paths"]["processed"]
    output_dir.mkdir(parents=True, exist_ok=True)
    if mode == "PILOT":
        processed_path = output_dir / "maisondelux_pilot_v3.csv"
    else:
        processed_path = output_dir / "maisondelux_clean_v3.csv"
    exact_duplicate = tuple(EXACT_DUPLICATE_PREFIXES)
    clean_rows = [
        row for row in rows
        if row.get("validation_status") in {"valid", "warning"}
        and not str(row.get("deduplication_status") or "").startswith(exact_duplicate)
    ]
    clean_object_ids = {id(row) for row in clean_rows}
    rejected_rows = [row for row in rows if id(row) not in clean_object_ids]
    pd.DataFrame(clean_rows, columns=V3_COLUMNS).to_csv(processed_path, index=False, encoding="utf-8")
    rejected_path = output_dir / ("maisondelux_pilot_rejected_v3.csv" if mode == "PILOT" else "maisondelux_rejected_v3.csv")
    pd.DataFrame(rejected_rows, columns=V3_COLUMNS).to_csv(rejected_path, index=False, encoding="utf-8")
    try:
        pd.DataFrame(clean_rows, columns=V3_COLUMNS).to_parquet(processed_path.with_suffix(".parquet"), index=False)
    except (ImportError, ModuleNotFoundError):
        pass
    stem = "pilot_quality_report_v3" if mode == "PILOT" else "data_quality_report_v3"
    json_path, md_path = write_report(report, config.project_root / settings["paths"]["reports"], stem)
    return RunResult(mode, len(selected_raw), len(rows), len(clean_rows), report.get("pilot_passed"), processed_path, json_path, md_path, statuses, report)


def run_pipeline(config: PipelineConfig | None = None) -> RunResult:
    config = config or PipelineConfig()
    settings = load_config(config.config_path)
    requested_mode = config.mode.upper()
    if requested_mode in {"FAST", "FULL"} and config.force_pilot_gate:
        pilot = _execute(config, settings, "PILOT")
        if not pilot.pilot_passed:
            failed = [name for name, passed in pilot.report["acceptance_checks"].items() if not passed]
            raise RuntimeError(
                "PILOT gate failed; FAST/FULL was not started and V3 final was not overwritten. "
                f"Failed checks: {', '.join(failed)}. See {pilot.report_markdown_path}"
            )
    return _execute(config, settings, requested_mode)


def summary_tables(result: RunResult) -> dict[str, pd.DataFrame]:
    report = result.report
    return {
        "summary": pd.DataFrame([report["summary"]]).T.rename(columns={0: "value"}),
        "missing_percent": pd.DataFrame.from_dict(report["missing_percent"], orient="index", columns=["missing_percent"]),
        "acceptance": pd.DataFrame.from_dict(report["acceptance_checks"], orient="index", columns=["passed"]),
        "property_type": pd.DataFrame.from_dict(report["distributions"]["property_type"], orient="index", columns=["count"]),
        "region": pd.DataFrame.from_dict(report["distributions"]["region"], orient="index", columns=["count"]),
        "city": pd.DataFrame.from_dict(report["distributions"]["city"], orient="index", columns=["count"]),
        "source": pd.DataFrame.from_dict(report["distributions"]["source"], orient="index", columns=["count"]),
    }
