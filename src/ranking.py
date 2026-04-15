"""Rank submissions, apply tie-breakers, mark top 10, and optional similarity flags."""

from __future__ import annotations

import logging
from typing import Final

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.models import EvaluationResult, RankedEvaluation, Submission

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD: Final[float] = 0.82


def _tie_break_key(sub: Submission, ev: EvaluationResult) -> tuple[int, int, int, int, str]:
    """
    Sort key for descending order (negate numeric fields).

    Tie-break order:
        1. Business Impact
        2. Feasibility & Scalability
        3. AI Depth & Creativity
        4. Stable submission_id (from structured submission)
    """
    b = ev.breakdown
    return (
        -ev.total_score,
        -b.business_impact.score,
        -b.feasibility_scalability.score,
        -b.ai_depth_creativity.score,
        sub.submission_id,
    )


def _combined_text(sub: Submission) -> str:
    parts = [
        sub.key_submission_impact,
        sub.business_use_case_and_impact,
        sub.solution_approach_overview,
    ]
    return " \n ".join(p for p in parts if p)


def annotate_similarity(submissions: list[Submission]) -> dict[str, list[str]]:
    """
    Build a map of submission_id -> list of other ids with high TF-IDF cosine similarity.

    This is advisory only; no rows are removed or merged.
    """
    texts = [_combined_text(s) for s in submissions]
    if len(texts) < 2:
        return {s.submission_id: [] for s in submissions}

    non_empty = [t if t.strip() else " " for t in texts]
    try:
        vectorizer = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
        matrix = vectorizer.fit_transform(non_empty)
        sim = np.asarray(cosine_similarity(matrix), dtype=float)
    except ValueError as exc:
        logger.warning("Similarity computation skipped: %s", exc)
        return {s.submission_id: [] for s in submissions}

    np.fill_diagonal(sim, 0.0)
    result: dict[str, list[str]] = {}
    ids = [s.submission_id for s in submissions]
    for i, sid in enumerate(ids):
        similar_idx = np.where(sim[i] >= SIMILARITY_THRESHOLD)[0]
        similar_ids = [ids[j] for j in similar_idx if j != i]
        result[sid] = sorted(set(similar_ids))
    return result


def rank_submissions(
    pairs: list[tuple[Submission, EvaluationResult]],
    top_n: int = 10,
) -> list[RankedEvaluation]:
    """
    Sort by total score (desc) with deterministic tie-breakers, mark top N shortlist.

    Args:
        pairs: (Submission, EvaluationResult) tuples in any order.
        top_n: Number of rows to mark as shortlisted (default 10).

    Returns:
        Ordered ``RankedEvaluation`` list (best rank first).
    """
    similarity_map = annotate_similarity([p[0] for p in pairs])

    decorated: list[tuple[tuple[int, int, int, int, str], Submission, EvaluationResult]] = []
    for sub, ev in pairs:
        key = _tie_break_key(sub, ev)
        decorated.append((key, sub, ev))

    decorated.sort(key=lambda x: x[0])

    ranked: list[RankedEvaluation] = []
    for rank, (_, sub, ev) in enumerate(decorated, start=1):
        sim_ids = similarity_map.get(sub.submission_id, [])
        ranked.append(
            RankedEvaluation(
                submission=sub,
                evaluation=ev,
                rank=rank,
                shortlisted=rank <= top_n,
                similar_submission_ids=sim_ids,
                similarity_flag=bool(sim_ids),
            )
        )
    return ranked
