"""FastAPI service exposing health, evaluation, and results endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.models import RankedEvaluation
from src.pipeline import load_session_results, run_pipeline
from src.utils import setup_logging

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hackathon Evaluator Agent",
    version="0.1.0",
    description="Stage 1 document-only hackathon evaluation API.",
)


class HealthResponse(BaseModel):
    """Simple health check payload."""

    status: str = Field(examples=["ok"])


class EvaluateRequest(BaseModel):
    """Request body for triggering a full evaluation run."""

    csv_path: str | None = Field(
        default=None,
        description="Optional absolute or project-relative CSV path.",
    )
    mock: bool = Field(
        default=False,
        description="If true, use deterministic mock scoring (no OpenAI calls).",
    )
    model: str | None = Field(
        default=None,
        description="Optional OpenAI model override for this run.",
    )


class EvaluateResponse(BaseModel):
    """Summary returned after a successful evaluation run."""

    status: str
    submissions_evaluated: int
    output_dir: str


def _resolve_csv_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        base = Path(__file__).resolve().parent.parent
        path = (base / path).resolve()
    return path


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness/readiness style health probe."""
    return HealthResponse(status="ok")


@app.post("/evaluate", response_model=EvaluateResponse)
def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    """
    Run the full pipeline: load CSV, call evaluator, rank, export artifacts.

    This can take several minutes for large CSVs in live mode.
    """
    csv_path = _resolve_csv_path(request.csv_path)
    try:
        ranked = run_pipeline(csv_path, mock=request.mock, model=request.model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Evaluation failed (runtime)")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Evaluation failed")
        raise HTTPException(status_code=500, detail="Evaluation failed") from exc

    base = Path(__file__).resolve().parent.parent / "output"
    return EvaluateResponse(
        status="ok",
        submissions_evaluated=len(ranked),
        output_dir=str(base),
    )


@app.get("/results", response_model=list[RankedEvaluation])
def results() -> list[RankedEvaluation]:
    """Return the latest ranked evaluations."""
    ranked = load_session_results()
    if not ranked:
        raise HTTPException(
            status_code=404,
            detail="No results found. Run POST /evaluate first.",
        )
    return ranked


@app.get("/top10", response_model=list[RankedEvaluation])
def top10() -> list[RankedEvaluation]:
    """Return the latest top-ten shortlist (``shortlisted`` flag true)."""
    ranked = load_session_results()
    if not ranked:
        raise HTTPException(
            status_code=404,
            detail="No results found. Run POST /evaluate first.",
        )
    return [r for r in ranked if r.shortlisted]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.api:app", host="0.0.0.0", port=8000, reload=True)
