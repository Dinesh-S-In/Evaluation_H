"""CLI entrypoint for previewing CSV data and running the evaluation pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.load_data import load_submissions, preview_data
from src.pipeline import preview_only, run_pipeline
from src.utils import setup_logging
from src.validate_data import validate_columns

logger = logging.getLogger(__name__)


def _cmd_preview(csv_path: Path | None) -> int:
    """Load CSV, validate columns, and print a short preview."""
    df = load_submissions(csv_path)
    validate_columns(df)
    preview_data(df)
    return 0


def _cmd_validate(csv_path: Path | None) -> int:
    """Validate CSV structure without printing a large preview."""
    preview_only(csv_path)
    logger.info("Validation succeeded.")
    return 0


def _cmd_evaluate(csv_path: Path | None, mock: bool, model: str | None) -> int:
    """Run the full LLM evaluation, ranking, and export pipeline."""
    run_pipeline(csv_path, mock=mock, model=model)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hackathon Stage 1 evaluator — CSV ingestion, LLM scoring, ranking, export.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Optional path to a submissions CSV (defaults to data/submissions.csv).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock scoring (no OpenAI API calls).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override OPENAI_MODEL for this run (live mode only).",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_prev = sub.add_parser("preview", help="Load CSV and print a preview.")
    p_prev.set_defaults(func=lambda args: _cmd_preview(Path(args.csv) if args.csv else None))

    p_val = sub.add_parser("validate", help="Validate required columns and non-empty CSV.")
    p_val.set_defaults(func=lambda args: _cmd_validate(Path(args.csv) if args.csv else None))

    p_eval = sub.add_parser("evaluate", help="Run evaluation + ranking + export.")
    p_eval.set_defaults(
        func=lambda args: _cmd_evaluate(Path(args.csv) if args.csv else None, args.mock, args.model)
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
