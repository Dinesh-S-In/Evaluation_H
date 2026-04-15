"""Shared utilities: logging setup and text normalization helpers."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging for CLI, API, and Streamlit entrypoints."""
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)


def normalize_whitespace(value: Any) -> str:
    """
    Convert a cell value to a stripped string with collapsed internal whitespace.

    NaN / None become empty strings.
    """
    if value is None:
        return ""
    if isinstance(value, float) and str(value) == "nan":
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", text)


def safe_str(value: Any) -> str:
    """Best-effort string for logging or display without raising."""
    try:
        return normalize_whitespace(value)
    except Exception:  # noqa: BLE001
        return ""
