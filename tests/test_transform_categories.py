"""Tests for category normalization and warnings."""

from __future__ import annotations

import pandas as pd

from src.transform import ALLOWED_CATEGORIES, dataframe_to_submissions


def test_category_exact_match() -> None:
    df = pd.DataFrame(
        {
            "Key Submission Impact": ["x"],
            "Business Use Case and Impact": ["x"],
            "Solution/Approach Overview": ["x"],
            "Category Selection": ["Data & Insights"],
            "Tools and Technology Used": ["x"],
        }
    )
    subs = dataframe_to_submissions(df)
    assert subs[0].category_valid is True
    assert subs[0].category_selection == "Data & Insights"


def test_category_compact_normalization() -> None:
    df = pd.DataFrame(
        {
            "Key Submission Impact": ["x"],
            "Business Use Case and Impact": ["x"],
            "Solution/Approach Overview": ["x"],
            "Category Selection": ["data and insights"],
            "Tools and Technology Used": ["x"],
        }
    )
    subs = dataframe_to_submissions(df)
    assert subs[0].category_valid is True
    assert subs[0].category_selection == "Data & Insights"


def test_invalid_category_marks_review() -> None:
    df = pd.DataFrame(
        {
            "Key Submission Impact": ["x"],
            "Business Use Case and Impact": ["x"],
            "Solution/Approach Overview": ["x"],
            "Category Selection": ["Not a real category"],
            "Tools and Technology Used": ["x"],
        }
    )
    subs = dataframe_to_submissions(df)
    assert subs[0].category_valid is False
    assert subs[0].category_warning
    assert subs[0].category_selection == "Not a real category"


def test_allowed_categories_count() -> None:
    assert len(ALLOWED_CATEGORIES) == 5
