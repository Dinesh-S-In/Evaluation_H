"""Validate submission CSV structure, normalize headers, and verify required columns."""

from __future__ import annotations

import logging
import re
from typing import Final

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS: Final[list[str]] = [
    "Key Submission Impact",
    "Business Use Case and Impact",
    "Solution/Approach Overview",
    "Category Selection",
    "Tools and Technology Used",
]

# Map normalized header text (lowercase, collapsed whitespace) to canonical CSV names.
_HEADER_ALIASES: Final[dict[str, str]] = {
    "solution / approach overview": "Solution/Approach Overview",
    "solution/ approach overview": "Solution/Approach Overview",
    "solution approach overview": "Solution/Approach Overview",
    "key submission impact": "Key Submission Impact",
    "business use case and impact": "Business Use Case and Impact",
    "category selection": "Category Selection",
    "tools and technology used": "Tools and Technology Used",
}


def normalize_column_label(name: object) -> str:
    """Strip BOM/whitespace and collapse internal whitespace in a CSV header label."""
    text = str(name).replace("\ufeff", "").strip()
    text = re.sub(r"\s+", " ", text)
    return text


def canonicalize_submission_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of ``df`` with cleaned headers and common column aliases resolved.

    Extra columns (for example ``Submission ID`` or ``Team Name``) are preserved.
    """
    out = df.copy()
    out.columns = [normalize_column_label(c) for c in out.columns]

    renames: dict[str, str] = {}
    for col in list(out.columns):
        key = col.lower()
        target = _HEADER_ALIASES.get(key)
        if target is None or col == target:
            continue
        if target in out.columns:
            logger.warning(
                "Keeping existing column %r; skipping alias column %r", target, col
            )
            continue
        renames[col] = target

    if renames:
        out = out.rename(columns=renames)
        logger.info("Canonicalized CSV headers: %s", renames)
    return out


def validate_columns(df: pd.DataFrame) -> None:
    """
    Verify that all required columns exist in the DataFrame.

    Raises:
        ValueError: If any required column is missing or the DataFrame is empty.
    """
    if df.empty:
        msg = "CSV file contains no data rows."
        logger.error(msg)
        raise ValueError(msg)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        msg = (
            f"Missing required columns: {missing}. "
            f"Found columns: {list(df.columns)}"
        )
        logger.error(msg)
        raise ValueError(msg)

    logger.info("All required columns are present.")
