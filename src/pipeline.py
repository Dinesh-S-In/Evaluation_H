"""End-to-end orchestration: load → validate → transform → evaluate → rank → export."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from src.config import (
    CSV_FILE_PATH,
    FINAL_SHORTLIST_CSV,
    FULL_RESULTS_CSV,
    FULL_RESULTS_XLSX,
    SESSION_RESULTS_JSON,
    TOP10_CSV,
    TOP10_XLSX,
    ensure_output_dir,
)
from src.evaluator import evaluate_submission
from src.exporter import build_results_dataframe, export_ranked_results
from src.load_data import load_submissions
from src.models import EvaluationResult, RankedEvaluation, Submission
from src.ranking import rank_submissions
from src.scoring import llm_payload_to_evaluation_result
from src.transform import dataframe_to_submissions
from src.validate_data import validate_columns

logger = logging.getLogger(__name__)


def run_evaluation_ranking(
    df: pd.DataFrame,
    *,
    mock: bool = False,
    model: str | None = None,
) -> list[RankedEvaluation]:
    """
    Validate CSV rows, run LLM (or mock) evaluation per submission, rank, and mark top 10.

    Unlike ``run_pipeline``, this does not write files — intended for serverless APIs.
    """
    validate_columns(df)
    submissions = dataframe_to_submissions(df)

    pairs: list[tuple[Submission, EvaluationResult]] = []
    for sub in submissions:
        payload = evaluate_submission(sub, mock=mock, model=model)
        result = llm_payload_to_evaluation_result(sub, payload)
        pairs.append((sub, result))

    return rank_submissions(pairs, top_n=10)


def run_pipeline(
    csv_path: Path | None = None,
    *,
    mock: bool = False,
    model: str | None = None,
) -> list[RankedEvaluation]:
    """
    Execute the full evaluation pipeline.

    Args:
        csv_path: Optional override CSV path (defaults to configured ``data/submissions.csv``).
        mock: Use mock evaluator instead of OpenAI.
        model: Optional OpenAI model override.

    Returns:
        Ranked evaluations, best rank first.
    """
    df = load_submissions(csv_path)
    ensure_output_dir()
    validate_columns(df)
    submissions = dataframe_to_submissions(df)

    pairs: list[tuple[Submission, EvaluationResult]] = []
    for sub in submissions:
        payload = evaluate_submission(sub, mock=mock, model=model)
        result = llm_payload_to_evaluation_result(sub, payload)
        pairs.append((sub, result))

    ranked = rank_submissions(pairs, top_n=10)
    export_ranked_results(
        ranked,
        full_csv=FULL_RESULTS_CSV,
        full_xlsx=FULL_RESULTS_XLSX,
        top10_csv=TOP10_CSV,
        top10_xlsx=TOP10_XLSX,
    )

    _write_session_json(ranked)
    logger.info("Pipeline complete: %s submissions ranked.", len(ranked))
    return ranked


def _write_session_json(ranked: list[RankedEvaluation]) -> None:
    """Persist last run for the FastAPI layer and external tools."""
    payload = [r.model_dump(mode="json") for r in ranked]
    try:
        SESSION_RESULTS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Failed to write session results JSON to %s", SESSION_RESULTS_JSON)
        raise


def load_session_results() -> list[RankedEvaluation]:
    """Load the most recently written session results from disk."""
    if not SESSION_RESULTS_JSON.exists():
        return []
    try:
        raw = SESSION_RESULTS_JSON.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read session results (%s): %s", SESSION_RESULTS_JSON, exc)
        return []
    if not isinstance(data, list):
        logger.warning("Session results JSON was not a list; ignoring.")
        return []

    ranked: list[RankedEvaluation] = []
    for idx, item in enumerate(data):
        try:
            ranked.append(RankedEvaluation.model_validate(item))
        except ValidationError as exc:
            logger.warning("Skipping invalid session row %s: %s", idx, exc)
    return ranked


def save_final_shortlist(ranked: list[RankedEvaluation], path: Path | None = None) -> Path:
    """
    Persist evaluator-approved shortlist (typically top 10 with manual overrides).

    Returns:
        Path written.
    """
    dest = path or FINAL_SHORTLIST_CSV

    df = build_results_dataframe(ranked)
    if "final_shortlisted" in df.columns:
        mask = df["final_shortlisted"].fillna(False).astype(bool)
        shortlisted = df.loc[mask].copy()
    elif "shortlisted" in df.columns:
        mask = df["shortlisted"].fillna(False).astype(bool)
        shortlisted = df.loc[mask].copy()
    else:
        shortlisted = df.head(10).copy()

    dest.parent.mkdir(parents=True, exist_ok=True)
    shortlisted.to_csv(dest, index=False)
    logger.info("Saved final shortlist to %s (%s rows)", dest, len(shortlisted))
    return dest


def preview_only(csv_path: Path | None = None) -> None:
    """Load and validate CSV for quick inspection (no LLM calls)."""
    path = csv_path or CSV_FILE_PATH
    df = load_submissions(path)
    validate_columns(df)
    subs = dataframe_to_submissions(df)
    logger.info("Preview OK: %s submission rows parsed.", len(subs))
