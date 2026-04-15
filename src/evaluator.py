"""LLM-backed submission evaluator with retries and a deterministic mock mode."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

from openai import OpenAI
from pydantic import ValidationError

from src.config import EVALUATION_PROMPT_PATH, SYSTEM_PROMPT_PATH
from src.models import LLMEvaluationPayload, Submission
from src.utils import safe_str

logger = logging.getLogger(__name__)

MAX_RETRIES: int = 3


@lru_cache(maxsize=2)
def _read_prompt_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        logger.error("Failed to read prompt file %s", path)
        raise RuntimeError(f"Prompt file not readable: {path}") from exc


def load_system_prompt() -> str:
    """Load the system prompt text from disk."""
    return _read_prompt_file(str(SYSTEM_PROMPT_PATH))


def load_evaluation_prompt_template() -> str:
    """Load the evaluation user-prompt template from disk."""
    return _read_prompt_file(str(EVALUATION_PROMPT_PATH))


def _submission_block(sub: Submission) -> str:
    team = sub.team_name or ""
    team_line = f"Team Name: {team}\n" if team else ""
    return (
        f"Submission ID: {sub.submission_id}\n"
        f"{team_line}"
        f"Category Selection: {sub.category_selection}\n"
        f"Key Submission Impact:\n{sub.key_submission_impact}\n\n"
        f"Business Use Case and Impact:\n{sub.business_use_case_and_impact}\n\n"
        f"Solution/Approach Overview:\n{sub.solution_approach_overview}\n\n"
        f"Tools and Technology Used:\n{sub.tools_and_technology_used}\n"
    )


def _mock_payload(sub: Submission) -> LLMEvaluationPayload:
    """Deterministic pseudo-scores for offline testing (no network calls)."""
    seed = sum(ord(c) for c in sub.submission_id + sub.solution_approach_overview[:120])
    bi = 16 + (seed % 25)   # 0–40 cap is enforced later; keep mid-high variety
    fs = 10 + (seed % 18)   # 0–30
    ad = 10 + (seed % 18)   # 0–30
    return LLMEvaluationPayload.model_validate(
        {
            "business_impact": {
                "score": bi,
                "reason": "Mock evaluation: impact inferred from written description only.",
            },
            "feasibility_scalability": {
                "score": fs,
                "reason": "Mock evaluation: feasibility based on described approach.",
            },
            "ai_depth_creativity": {
                "score": ad,
                "reason": "Mock evaluation: AI depth estimated from tools and narrative.",
            },
            "total_score": bi + fs + ad,
            "final_summary": "Mock mode: no live model call was made.",
            "shortlist_recommendation": "Yes" if (bi + fs + ad) >= 75 else "No",
        }
    )


def _extract_json_object_text(content: str) -> str:
    """
    Extract a JSON object substring from a model response.

    Handles optional markdown fences and leading/trailing non-JSON chatter.
    """
    text = content.strip().replace("\ufeff", "")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return text[start : end + 1]


def _parse_llm_json(content: str) -> LLMEvaluationPayload:
    """Parse model output into a strict Pydantic payload."""
    json_text = _extract_json_object_text(content)
    data: Any = json.loads(json_text)
    if not isinstance(data, dict):
        raise TypeError("Expected a JSON object at the top level")
    # Defensive: if a model includes legacy keys, strip to what our schema expects.
    allowed = {
        "business_impact",
        "feasibility_scalability",
        "ai_depth_creativity",
        "total_score",
        "final_summary",
        "shortlist_recommendation",
    }
    data = {k: v for k, v in data.items() if k in allowed}
    return LLMEvaluationPayload.model_validate(data)


def evaluate_submission(
    submission: Submission,
    *,
    mock: bool = False,
    model: str | None = None,
) -> LLMEvaluationPayload:
    """
    Evaluate a single submission using OpenAI or mock data.

    Args:
        submission: Structured submission text.
        mock: When True, skip API calls and return deterministic mock scores.
        model: OpenAI model name; defaults to ``OPENAI_MODEL`` env or ``gpt-4o-mini``.

    Returns:
        Parsed ``LLMEvaluationPayload``.

    Raises:
        RuntimeError: If evaluation fails after retries (live mode only).
        ValueError: If ``OPENAI_API_KEY`` is missing in live mode.
    """
    if mock or os.getenv("MOCK_EVALUATION", "").lower() in {"1", "true", "yes"}:
        logger.info("Mock evaluation for %s", submission.submission_id)
        return _mock_payload(submission)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Use mock mode (--mock) for offline runs."
        )

    resolved_model = (model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
    system = load_system_prompt()
    template = load_evaluation_prompt_template()
    user_content = template.replace("{{SUBMISSION_BLOCK}}", _submission_block(submission))

    client = OpenAI(api_key=api_key)
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        message = ""
        try:
            response = client.chat.completions.create(
                model=resolved_model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
            if not response.choices:
                raise RuntimeError("OpenAI response contained no choices")
            message = response.choices[0].message.content or ""
            payload = _parse_llm_json(message)
            logger.info(
                "Evaluated %s on attempt %s (model=%s)",
                submission.submission_id,
                attempt,
                resolved_model,
            )
            return payload
        except (json.JSONDecodeError, ValidationError, IndexError, TypeError, ValueError) as exc:
            last_error = exc
            snippet = safe_str(message)[:400]
            logger.warning(
                "Attempt %s/%s failed for %s: %s | output_snippet=%r",
                attempt,
                MAX_RETRIES,
                submission.submission_id,
                exc,
                snippet,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.exception(
                "OpenAI request error for %s on attempt %s",
                submission.submission_id,
                attempt,
            )

    raise RuntimeError(
        f"Failed to evaluate submission {submission.submission_id} after "
        f"{MAX_RETRIES} attempts: {last_error}"
    ) from last_error


def redact_secrets_for_log(value: str, max_len: int = 200) -> str:
    """Trim strings for logs without echoing large payloads or secrets."""
    text = safe_str(value)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text
