"""Tests for CSV column validation."""

from __future__ import annotations

import pandas as pd
import pytest

from src.validate_data import (
    REQUIRED_COLUMNS,
    canonicalize_submission_columns,
    validate_columns,
)


def test_validate_columns_success() -> None:
    df = pd.DataFrame({col: ["x"] for col in REQUIRED_COLUMNS})
    validate_columns(df)


def test_validate_columns_missing() -> None:
    df = pd.DataFrame({"wrong": [1]})
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_columns(df)


def test_validate_columns_empty() -> None:
    df = pd.DataFrame(columns=REQUIRED_COLUMNS)
    with pytest.raises(ValueError, match="no data rows"):
        validate_columns(df)


def test_canonicalize_alias_solution_column() -> None:
    df = pd.DataFrame(
        {
            "Key Submission Impact": ["a"],
            "Business Use Case and Impact": ["b"],
            "Solution / Approach Overview": ["c"],
            "Category Selection": ["Innovation"],
            "Tools and Technology Used": ["d"],
        }
    )
    fixed = canonicalize_submission_columns(df)
    validate_columns(fixed)
    assert "Solution/Approach Overview" in fixed.columns
