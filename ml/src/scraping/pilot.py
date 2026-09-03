"""Run bounded, policy-gated source preflights and write an audit record."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ml.src.scraping.adapters import adapters


ROOT = Path(__file__).resolve().parents[3]


def run_pilots() -> list[dict]:
    results = []
    for adapter in adapters():
        result = asdict(adapter.preflight())
        result.update({
            "base_url": adapter.policy.base_url,
            "robots_url": adapter.policy.robots_url,
            "terms_url": adapter.policy.terms_url,
            "permitted_use": adapter.policy.permitted_use,
            "authorization_reference": adapter.policy.authorization_reference,
        })
        results.append(result)
    path = ROOT / "reports" / "scraping" / "source_policy_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    results = run_pilots()
    print(json.dumps({item["source"]: item["status"] for item in results}, sort_keys=True))
