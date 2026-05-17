"""
utils/api_client.py
───────────────────
Thin wrapper around the FastAPI backend.  Every method raises on HTTP error
so callers can catch and display the message cleanly in Streamlit.
"""
from __future__ import annotations

from typing import IO, List, Tuple

import requests


class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base = base_url.rstrip("/")
        self._session = requests.Session()

    # ── Health ────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        r = self._session.get(f"{self.base}/api/health", timeout=5)
        r.raise_for_status()
        return r.json()

    # ── Analyze ───────────────────────────────────────────────────────────────

    def analyze(
        self,
        root_url: str,
        har_files: List,  # Streamlit UploadedFile objects
    ) -> dict:
        files = [
            ("har_files", (f.name, f.read(), "application/octet-stream"))
            for f in har_files
        ]
        data = {"root_url": root_url}
        r = self._session.post(
            f"{self.base}/api/analyze",
            data=data,
            files=files,
            timeout=120,
        )
        _raise(r)
        return r.json()

    # ── Auth filter ───────────────────────────────────────────────────────────

    def filter_auth(self, tree_payload: dict) -> dict:
        r = self._session.post(
            f"{self.base}/api/filter-auth",
            json=tree_payload,
            timeout=60,
        )
        _raise(r)
        return r.json()

    # ── Custom filter ─────────────────────────────────────────────────────────

    def filter_custom(self, tree_payload: dict, config: dict) -> dict:
        body = {**tree_payload, "config": config}
        r = self._session.post(
            f"{self.base}/api/filter-custom",
            json=body,
            timeout=60,
        )
        _raise(r)
        return r.json()

    # ── Default filter config ─────────────────────────────────────────────────

    def get_default_filter(self) -> dict:
        r = self._session.get(f"{self.base}/api/default-filter", timeout=10)
        _raise(r)
        return r.json()

    # ── Validate config ───────────────────────────────────────────────────────

    def validate_filter_config(self, config: dict) -> dict:
        r = self._session.post(
            f"{self.base}/api/validate-filter-config",
            json=config,
            timeout=10,
        )
        _raise(r)
        return r.json()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _raise(response: requests.Response):
    if response.ok:
        return
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text
    raise RuntimeError(f"API {response.status_code}: {detail}")
