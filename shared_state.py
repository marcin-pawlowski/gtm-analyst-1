"""
Shared State
============
Persistent state store for the GTM Analyst multi-agent system.
Uses a local JSON file so state survives across sub-agent calls within a session.
"""
from __future__ import annotations
import json
from pathlib import Path

_STATE_FILE = Path(".gtm_audit_state.json")

_DEFAULTS: dict = {
    "gtm_data": None,
    "filename": None,
    "analysis": None,
    "author": {"name": None, "title": None, "email": None},
    "report_paths": [],
}


def _load() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULTS)


def _save(state: dict) -> None:
    _STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── GTM data ──────────────────────────────────────────────────────────────────

def set_gtm_data(filename: str, data: dict) -> None:
    s = _load()
    s["gtm_data"] = data
    s["filename"] = filename
    # Clear stale analysis when a new file is loaded
    s["analysis"] = None
    s["report_paths"] = []
    _save(s)


def get_gtm_data() -> dict | None:
    return _load().get("gtm_data")


def get_filename() -> str | None:
    return _load().get("filename")


# ── Analysis ──────────────────────────────────────────────────────────────────

def set_analysis(results: dict) -> None:
    s = _load()
    s["analysis"] = results
    _save(s)


def get_analysis() -> dict | None:
    return _load().get("analysis")


# ── Author ────────────────────────────────────────────────────────────────────

def set_author(name: str, title: str, email: str) -> None:
    s = _load()
    s["author"] = {"name": name, "title": title, "email": email}
    _save(s)


def get_author() -> dict:
    return _load().get("author", {})


# ── Report paths ──────────────────────────────────────────────────────────────

def add_report_path(path: str) -> None:
    s = _load()
    paths: list = s.get("report_paths", [])
    if path not in paths:
        paths.append(path)
    s["report_paths"] = paths
    _save(s)


def get_report_paths() -> list[str]:
    return _load().get("report_paths", [])


# ── Utility ───────────────────────────────────────────────────────────────────

def clear_all() -> None:
    """Wipes all state — useful when starting a fresh audit."""
    _save(dict(_DEFAULTS))
