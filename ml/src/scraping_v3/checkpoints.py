"""Append-only JSONL checkpoints with deterministic resume keys."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from .schema import canonical_url, clean_text, normalized


def record_key(record: dict[str, Any]) -> str | None:
    source = normalized(record.get("source"))
    native = clean_text(record.get("source_listing_id") or record.get("native_id") or record.get("id"))
    if source and native:
        return f"id:{source}:{native}"
    url = canonical_url(record.get("url") or record.get("listing_url"))
    return f"url:{url}" if url else None


class JsonlCheckpoint:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.keys: set[str] = set()
        self.rows = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    # A crash can leave only the final line incomplete.
                    continue
                self.rows += 1
                key = record_key(row)
                if key:
                    self.keys.add(key)

    def append_batch(self, records: Iterable[dict[str, Any]]) -> int:
        accepted: list[dict[str, Any]] = []
        for record in records:
            key = record_key(record)
            if key and key in self.keys:
                continue
            accepted.append(record)
            if key:
                self.keys.add(key)
        if not accepted:
            return 0
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            for record in accepted:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.rows += len(accepted)
        return len(accepted)

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records
