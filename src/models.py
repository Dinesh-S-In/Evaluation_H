"""Pydantic models for submissions, LLM output, and ranked evaluation records."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Submission(BaseModel):
    """Structured submission parsed from one CSV row."""

    submission_id: str = Field(..., description="Stable identifier for this row.")
    row_index: int = Field(..., ge=0, description="Zero-based index in the loaded DataFrame.")
    team_name: str | None = Field(
        default=None,
        description="Optional team name from CSV when provided.",
    )
    key_submission_impact: str
    business_use_case_and_impact: str
    solution_approach_overview: str
    category_selection: str
    tools_and_technology_used: str
    category_valid: bool = Field(
        default=True,
        description="False if category text does not match an allowed category.",
    )
    category_warning: str | None = Field(
        default=None,
        description="Human-readable warning when category is invalid or ambiguous.",
    )


class CriterionScore(BaseModel):
    """Score and rationale for a single judging criterion."""

    model_config = ConfigDict(extra="ignore")

    score: int = Field(..., ge=0)
    reason: str = Field(default="", max_length=4000)

    @field_validator("reason", mode="before")
    @classmethod
    def _coerce_reason(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)


class EvaluationBreakdown(BaseModel):
    """Per-criterion scores returned by the LLM (before code-side clamping)."""

    model_config = ConfigDict(extra="ignore")

    business_impact: CriterionScore
    feasibility_scalability: CriterionScore
    ai_depth_creativity: CriterionScore


class LLMEvaluationPayload(BaseModel):
    """
    Full JSON object expected from the LLM.

    Note: ``total_score`` from the model is informational only; the application
    recomputes the total from clamped criterion scores.
    """

    model_config = ConfigDict(extra="ignore")

    business_impact: CriterionScore
    feasibility_scalability: CriterionScore
    ai_depth_creativity: CriterionScore
    total_score: int = Field(default=0, ge=0, le=100)
    final_summary: str = ""
    shortlist_recommendation: Literal["Yes", "No"] = "No"

    @field_validator("final_summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value)

    @field_validator("shortlist_recommendation", mode="before")
    @classmethod
    def _coerce_shortlist(cls, value: object) -> Literal["Yes", "No"]:
        if value is None:
            return "No"
        text = str(value).strip().lower()
        if text in {"yes", "y", "true", "1"}:
            return "Yes"
        if text in {"no", "n", "false", "0"}:
            return "No"
        return "No"

    @field_validator(
        "business_impact",
        "feasibility_scalability",
        "ai_depth_creativity",
        mode="before",
    )
    @classmethod
    def _coerce_criterion(cls, value: object) -> object:
        if isinstance(value, dict) and "score" in value:
            score = value.get("score")
            if isinstance(score, (float, str, int)):
                try:
                    coerced = int(round(float(str(score))))
                except (TypeError, ValueError):
                    coerced = 0
                value = {**value, "score": max(0, coerced)}
        return value


class EvaluationResult(BaseModel):
    """Authoritative evaluation after bounds checks and total recomputation."""

    model_config = ConfigDict(extra="ignore")

    submission_id: str
    row_index: int
    breakdown: EvaluationBreakdown
    total_score: int = Field(..., ge=0, le=100)
    final_summary: str = ""
    shortlist_recommendation: Literal["Yes", "No"] = "No"
    model_reported_total: int | None = Field(
        default=None,
        description="Original total_score field from the LLM, if any.",
    )


class RankedEvaluation(BaseModel):
    """Evaluation plus rank, shortlist flag, and optional similarity metadata."""

    model_config = ConfigDict(extra="ignore")

    submission: Submission
    evaluation: EvaluationResult
    rank: int = Field(..., ge=1)
    shortlisted: bool = False
    similar_submission_ids: list[str] = Field(default_factory=list)
    similarity_flag: bool = Field(
        default=False,
        description="True if this submission is highly similar to at least one other.",
    )
    manual_total_score: int | None = Field(
        default=None,
        description="Optional evaluator override for the displayed/final total score.",
    )
    evaluator_notes: str | None = Field(
        default=None,
        description="Free-form notes from a human reviewer.",
    )
    manual_shortlisted: bool | None = Field(
        default=None,
        description="When set, overrides the automatic top-N shortlist flag for exports and review.",
    )

    def effective_shortlisted(self) -> bool:
        """Return the shortlist flag after applying any manual override."""
        if self.manual_shortlisted is not None:
            return self.manual_shortlisted
        return self.shortlisted

    def has_manual_edits(self) -> bool:
        """True if an evaluator changed score, notes, or shortlist from defaults."""
        notes = (self.evaluator_notes or "").strip()
        return (
            self.manual_total_score is not None
            or bool(notes)
            or self.manual_shortlisted is not None
        )
