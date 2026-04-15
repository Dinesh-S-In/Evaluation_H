"""Map CSV rows into structured ``Submission`` models with category validation."""

from __future__ import annotations

import logging
import re
from typing import Final

import pandas as pd

from src.models import Submission
from src.utils import normalize_whitespace

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES: Final[list[str]] = [
    "Productivity Boost",
    "Client Delivery",
    "Data & Insights",
    "Innovation",
    "Cross-Platform Collaboration",
]

_CANONICAL_LOWER: Final[dict[str, str]] = {c.lower(): c for c in ALLOWED_CATEGORIES}
_CANONICAL_COMPACT: Final[dict[str, str]] = {
    re.sub(r"[^a-z0-9]+", "", c.lower()): c for c in ALLOWED_CATEGORIES
}


def _resolve_category(raw: str) -> tuple[bool, str, str]:
    """
    Match user-provided category text to an allowed canonical category.

    Returns:
        Tuple of (is_valid, canonical_or_original, warning_message_or_empty).
    """
    cleaned = normalize_whitespace(raw)
    if not cleaned:
        return False, "", "Category Selection is empty; requires manual review."

    key = cleaned.lower()
    if key in _CANONICAL_LOWER:
        return True, _CANONICAL_LOWER[key], ""

    compact = re.sub(r"[^a-z0-9]+", "", key)
    if compact in _CANONICAL_COMPACT:
        return True, _CANONICAL_COMPACT[compact], ""

    for allowed_lower, canonical in _CANONICAL_LOWER.items():
        if allowed_lower in key or key in allowed_lower:
            return True, canonical, ""

    return False, cleaned, (
        f"Category '{cleaned}' does not match any allowed category "
        f"({', '.join(ALLOWED_CATEGORIES)}). Marked for review."
    )


def _unique_submission_id(base: str, used: set[str], fallback: str) -> str:
    """Ensure ``submission_id`` values remain unique within a single import."""
    candidate = (base or "").strip() or fallback
    if candidate not in used:
        used.add(candidate)
        return candidate
    suffix = 2
    while True:
        candidate_n = f"{candidate}__{suffix}"
        if candidate_n not in used:
            used.add(candidate_n)
            return candidate_n
        suffix += 1


def dataframe_to_submissions(df: pd.DataFrame) -> list[Submission]:
    """
    Convert a validated submissions DataFrame into ``Submission`` objects.

    Invalid categories produce warnings but do not stop processing.
    """
    submissions: list[Submission] = []
    used_ids: set[str] = set()
    for pos in range(len(df)):
        row = df.iloc[pos]
        key_impact = normalize_whitespace(row.get("Key Submission Impact", ""))
        business = normalize_whitespace(row.get("Business Use Case and Impact", ""))
        solution = normalize_whitespace(row.get("Solution/Approach Overview", ""))
        category_raw = normalize_whitespace(row.get("Category Selection", ""))
        tools = normalize_whitespace(row.get("Tools and Technology Used", ""))

        valid, canonical_category, warning = _resolve_category(category_raw)
        if warning:
            logger.warning("Row %s: %s", pos + 1, warning)

        raw_id = normalize_whitespace(row.get("Submission ID", ""))
        fallback = f"SUB-{pos + 1:04d}"
        submission_id = _unique_submission_id(raw_id, used_ids, fallback)

        team_raw = row.get("Team Name", "")
        team_name = normalize_whitespace(team_raw) or None

        submissions.append(
            Submission(
                submission_id=submission_id,
                row_index=pos,
                team_name=team_name,
                key_submission_impact=key_impact,
                business_use_case_and_impact=business,
                solution_approach_overview=solution,
                category_selection=canonical_category or category_raw,
                tools_and_technology_used=tools,
                category_valid=valid,
                category_warning=warning or None,
            )
        )
    return submissions
