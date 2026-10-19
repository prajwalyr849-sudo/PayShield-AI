"""Safely diagnose the backend Endless Search configuration and API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPOSITORY_ROOT / ".env"
SEARCH_URL = "https://search.endless.sbs/api/v1/search"
SEARCH_QUERY = "wireless headphones"
REQUEST_TIMEOUT_SECONDS = 10


def _load_backend_environment() -> str:
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    return os.getenv("ENDLESS_SEARCH_KEY", "").strip()


def _result_count(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    results = payload.get("results")
    return len(results) if isinstance(results, list) else 0


def diagnose() -> dict[str, str | int]:
    api_key = _load_backend_environment()
    report: dict[str, str | int] = {
        "API key configured": "YES" if api_key else "NO",
        "Search provider reachable": "NOT TESTED",
        "API authentication accepted": "NOT TESTED",
        "Search request successful": "NOT TESTED",
        "Number of results returned": 0,
    }

    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        response = requests.get(
            SEARCH_URL,
            headers=headers,
            params={"q": SEARCH_QUERY, "type": "web"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        report["Search provider reachable"] = "NO"
        return report

    report["Search provider reachable"] = "YES"
    if response.status_code in {401, 403}:
        report["API authentication accepted"] = "NO"
    elif 200 <= response.status_code < 300:
        report["API authentication accepted"] = "YES"
    else:
        report["API authentication accepted"] = "NOT TESTED"

    if not 200 <= response.status_code < 300:
        return report

    try:
        payload = response.json()
    except ValueError:
        return report

    count = _result_count(payload)
    report["Number of results returned"] = count
    report["Search request successful"] = "YES" if count > 0 else "NO"
    return report


if __name__ == "__main__":
    for label, value in diagnose().items():
        print(f"{label}: {value}")
