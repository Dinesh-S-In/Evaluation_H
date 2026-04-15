"""Tests for score clamping and total recomputation."""

from __future__ import annotations

import pytest

from src.models import (
    CriterionScore,
    EvaluationBreakdown,
    LLMEvaluationPayload,
    Submission,
)
from src.scoring import SCORE_CAPS, assert_scores_within_bounds, llm_payload_to_evaluation_result


def _sample_submission() -> Submission:
    return Submission(
        submission_id="SUB-0001",
        row_index=0,
        key_submission_impact="k",
        business_use_case_and_impact="b",
        solution_approach_overview="s",
        category_selection="Innovation",
        tools_and_technology_used="t",
        category_valid=True,
        category_warning=None,
    )


def test_clamps_high_scores() -> None:
    payload = LLMEvaluationPayload.model_validate(
        {
            "business_impact": {"score": 99, "reason": "x"},
            "feasibility_scalability": {"score": 99, "reason": "x"},
            "ai_depth_creativity": {"score": 99, "reason": "x"},
            "innovation": {"score": 99, "reason": "x"},
            "cross_platform_collaboration": {"score": 99, "reason": "x"},
            "clarity": {"score": 99, "reason": "x"},
            "total_score": 999,
            "final_summary": "summary",
            "shortlist_recommendation": "No",
        }
    )
    sub = _sample_submission()
    result = llm_payload_to_evaluation_result(sub, payload)
    b = result.breakdown
    assert b.business_impact.score == SCORE_CAPS["business_impact"]
    assert b.feasibility_scalability.score == SCORE_CAPS["feasibility_scalability"]
    assert b.ai_depth_creativity.score == SCORE_CAPS["ai_depth_creativity"]
    assert b.innovation.score == SCORE_CAPS["innovation"]
    assert b.cross_platform_collaboration.score == SCORE_CAPS["cross_platform_collaboration"]
    assert b.clarity.score == SCORE_CAPS["clarity"]
    expected = sum(SCORE_CAPS.values())
    assert result.total_score == expected == 100
    assert_scores_within_bounds(result)


def test_recomputes_total_ignores_model_sum() -> None:
    payload = LLMEvaluationPayload(
        business_impact=CriterionScore(score=10, reason=""),
        feasibility_scalability=CriterionScore(score=10, reason=""),
        ai_depth_creativity=CriterionScore(score=10, reason=""),
        innovation=CriterionScore(score=10, reason=""),
        cross_platform_collaboration=CriterionScore(score=5, reason=""),
        clarity=CriterionScore(score=5, reason=""),
        total_score=12,
        final_summary="",
        shortlist_recommendation="No",
    )
    result = llm_payload_to_evaluation_result(_sample_submission(), payload)
    assert result.total_score == 50
    assert result.model_reported_total == 12
