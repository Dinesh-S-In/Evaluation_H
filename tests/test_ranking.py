"""Tests for ranking order and tie-breakers."""

from __future__ import annotations

from src.models import (
    CriterionScore,
    EvaluationBreakdown,
    EvaluationResult,
    Submission,
)
from src.ranking import rank_submissions


def _submission(sid: str, row: int) -> Submission:
    return Submission(
        submission_id=sid,
        row_index=row,
        key_submission_impact="",
        business_use_case_and_impact="",
        solution_approach_overview="",
        category_selection="Innovation",
        tools_and_technology_used="",
        category_valid=True,
        category_warning=None,
    )


def _evaluation(
    sid: str,
    row: int,
    *,
    total: int,
    bi: int,
    fs: int,
    ad: int,
    cl: int,
) -> EvaluationResult:
    breakdown = EvaluationBreakdown(
        business_impact=CriterionScore(score=bi, reason=""),
        feasibility_scalability=CriterionScore(score=fs, reason=""),
        ai_depth_creativity=CriterionScore(score=ad, reason=""),
        innovation=CriterionScore(score=0, reason=""),
        cross_platform_collaboration=CriterionScore(score=0, reason=""),
        clarity=CriterionScore(score=cl, reason=""),
    )
    return EvaluationResult(
        submission_id=sid,
        row_index=row,
        breakdown=breakdown,
        total_score=total,
        final_summary="",
        shortlist_recommendation="No",
        model_reported_total=None,
    )


def test_ranking_descending_total() -> None:
    pairs = [
        (_submission("SUB-0001", 0), _evaluation("SUB-0001", 0, total=50, bi=10, fs=10, ad=10, cl=10)),
        (_submission("SUB-0002", 1), _evaluation("SUB-0002", 1, total=80, bi=10, fs=10, ad=10, cl=10)),
    ]
    ranked = rank_submissions(pairs, top_n=10)
    assert [r.submission.submission_id for r in ranked] == ["SUB-0002", "SUB-0001"]


def test_tie_breaker_prefers_higher_business_impact() -> None:
    pairs = [
        (_submission("A", 0), _evaluation("A", 0, total=70, bi=10, fs=20, ad=20, cl=10)),
        (_submission("B", 1), _evaluation("B", 1, total=70, bi=20, fs=10, ad=20, cl=10)),
    ]
    ranked = rank_submissions(pairs, top_n=10)
    assert ranked[0].submission.submission_id == "B"


def test_tie_breaker_second_level_feasibility() -> None:
    pairs = [
        (_submission("A", 0), _evaluation("A", 0, total=70, bi=15, fs=10, ad=20, cl=10)),
        (_submission("B", 1), _evaluation("B", 1, total=70, bi=15, fs=18, ad=5, cl=10)),
    ]
    ranked = rank_submissions(pairs, top_n=10)
    assert ranked[0].submission.submission_id == "B"


def test_tie_breaker_third_level_ai_depth() -> None:
    pairs = [
        (_submission("A", 0), _evaluation("A", 0, total=70, bi=15, fs=15, ad=10, cl=10)),
        (_submission("B", 1), _evaluation("B", 1, total=70, bi=15, fs=15, ad=18, cl=1)),
    ]
    ranked = rank_submissions(pairs, top_n=10)
    assert ranked[0].submission.submission_id == "B"


def test_tie_breaker_fourth_level_clarity() -> None:
    pairs = [
        (_submission("A", 0), _evaluation("A", 0, total=70, bi=15, fs=15, ad=15, cl=5)),
        (_submission("B", 1), _evaluation("B", 1, total=70, bi=15, fs=15, ad=15, cl=9)),
    ]
    ranked = rank_submissions(pairs, top_n=10)
    assert ranked[0].submission.submission_id == "B"


def test_top10_shortlist_flag() -> None:
    pairs = []
    for i in range(12):
        sid = f"SUB-{i:04d}"
        pairs.append(
            (
                _submission(sid, i),
                _evaluation(sid, i, total=100 - i, bi=5, fs=5, ad=5, cl=5),
            )
        )
    ranked = rank_submissions(pairs, top_n=10)
    assert sum(1 for r in ranked if r.shortlisted) == 10
    assert ranked[0].shortlisted is True
    assert ranked[9].shortlisted is True
    assert ranked[10].shortlisted is False
