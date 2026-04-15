"""Clamp LLM criterion scores, validate bounds, and recompute totals in code."""

from __future__ import annotations

import logging
from typing import Final

from src.models import (
    CriterionScore,
    EvaluationBreakdown,
    EvaluationResult,
    LLMEvaluationPayload,
    Submission,
)

logger = logging.getLogger(__name__)

SCORE_CAPS: Final[dict[str, int]] = {
    "business_impact": 40,
    "feasibility_scalability": 30,
    "ai_depth_creativity": 30,
}


def _clamp(name: str, score: int, cap: int) -> int:
    if score < 0:
        logger.warning("Criterion %s score %s below 0; clamped to 0.", name, score)
        return 0
    if score > cap:
        logger.warning(
            "Criterion %s score %s exceeds cap %s; clamped.", name, score, cap
        )
        return cap
    return score


def llm_payload_to_evaluation_result(
    submission: Submission,
    payload: LLMEvaluationPayload,
) -> EvaluationResult:
    """
    Build an authoritative ``EvaluationResult`` with clamped scores and recomputed total.

    The model-supplied ``total_score`` is stored for audit but not trusted for ranking.
    """
    bi = _clamp(
        "business_impact",
        payload.business_impact.score,
        SCORE_CAPS["business_impact"],
    )
    fs = _clamp(
        "feasibility_scalability",
        payload.feasibility_scalability.score,
        SCORE_CAPS["feasibility_scalability"],
    )
    ad = _clamp(
        "ai_depth_creativity",
        payload.ai_depth_creativity.score,
        SCORE_CAPS["ai_depth_creativity"],
    )

    breakdown = EvaluationBreakdown(
        business_impact=CriterionScore(score=bi, reason=payload.business_impact.reason),
        feasibility_scalability=CriterionScore(
            score=fs, reason=payload.feasibility_scalability.reason
        ),
        ai_depth_creativity=CriterionScore(
            score=ad, reason=payload.ai_depth_creativity.reason
        ),
    )

    total = bi + fs + ad
    if total > 100:
        logger.error("Recomputed total %s exceeds 100; capping.", total)
        total = 100

    return EvaluationResult(
        submission_id=submission.submission_id,
        row_index=submission.row_index,
        breakdown=breakdown,
        total_score=total,
        final_summary=payload.final_summary,
        shortlist_recommendation=payload.shortlist_recommendation,
        model_reported_total=payload.total_score,
    )


def assert_scores_within_bounds(result: EvaluationResult) -> None:
    """Assert helper for tests — ensures all scores respect caps."""
    b = result.breakdown
    assert 0 <= b.business_impact.score <= SCORE_CAPS["business_impact"]
    assert 0 <= b.feasibility_scalability.score <= SCORE_CAPS["feasibility_scalability"]
    assert 0 <= b.ai_depth_creativity.score <= SCORE_CAPS["ai_depth_creativity"]
    assert 0 <= result.total_score <= 100
