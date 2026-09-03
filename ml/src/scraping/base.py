"""Common source adapter contract and conservative HTTP client."""
from __future__ import annotations

import json
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests


@dataclass(frozen=True)
class SourcePolicy:
    source: str
    base_url: str
    robots_url: str
    terms_url: str | None
    enabled: bool
    permitted_use: str
    reason: str
    authorization_reference: str | None = None


@dataclass
class PilotResult:
    source: str
    status: str
    robots_status: str
    pilot_status: str
    reason: str
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    http_status: int | None = None
    records: list[dict[str, Any]] = field(default_factory=list)


class ConservativeHttpClient:
    def __init__(self, user_agent: str = "MaisonDeLUX-data-pipeline/1.0", timeout: float = 20,
                 max_attempts: int = 3, minimum_delay: float = 1.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.minimum_delay = minimum_delay
        self.last_request: dict[str, float] = {}
        self.circuit_open: set[str] = set()

    def get(self, url: str) -> requests.Response:
        domain = urlsplit(url).netloc.casefold()
        if domain in self.circuit_open:
            raise RuntimeError(f"Circuit open for {domain}")
        elapsed = time.monotonic() - self.last_request.get(domain, 0)
        if elapsed < self.minimum_delay:
            time.sleep(self.minimum_delay - elapsed)
        for attempt in range(1, self.max_attempts + 1):
            response = self.session.get(url, timeout=self.timeout)
            self.last_request[domain] = time.monotonic()
            if response.status_code == 200:
                return response
            if response.status_code in {401, 403, 429}:
                self.circuit_open.add(domain)
                raise RuntimeError(f"Access circuit opened after HTTP {response.status_code} for {domain}")
            if response.status_code < 500 or attempt == self.max_attempts:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            delay = min(60.0, 2 ** (attempt - 1) + random.random())
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        delay = max(delay, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                    except (TypeError, ValueError):
                        pass
            time.sleep(max(0.0, delay))
        raise RuntimeError(f"Exhausted retries for {url}")


class SourceAdapter(ABC):
    def __init__(self, policy: SourcePolicy, client: ConservativeHttpClient | None = None):
        self.policy = policy
        self.client = client or ConservativeHttpClient()

    def robots_allows(self, url: str) -> tuple[bool, str]:
        try:
            response = self.client.get(self.policy.robots_url)
        except Exception as error:
            return False, f"robots_unavailable:{type(error).__name__}"
        parser = RobotFileParser()
        parser.set_url(self.policy.robots_url)
        parser.parse(response.text.splitlines())
        return parser.can_fetch(self.client.session.headers["User-Agent"], url), f"http_{response.status_code}"

    def preflight(self) -> PilotResult:
        allowed, robots_status = self.robots_allows(self.policy.base_url)
        if not self.policy.enabled:
            return PilotResult(self.policy.source, "disabled", robots_status, "not_run", self.policy.reason)
        if not allowed:
            return PilotResult(self.policy.source, "disabled", robots_status, "blocked_by_robots", "robots.txt does not permit the pilot URL")
        return self.pilot()

    @abstractmethod
    def pilot(self) -> PilotResult:
        raise NotImplementedError

    @abstractmethod
    def collect(self, checkpoint: Path, limit: int | None = None) -> Iterable[dict[str, Any]]:
        raise NotImplementedError


def write_checkpoint(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            count += 1
    return count
