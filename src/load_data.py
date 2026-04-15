"""Load hackathon submission CSV files into pandas DataFrames."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd

from src.config import CSV_FILE_PATH
from src.validate_data import canonicalize_submission_columns

logger = logging.getLogger(__name__)


def load_submissions(csv_path: Path | None = None) -> pd.DataFrame:
    """
    Load hackathon submissions from a CSV file.

    Args:
        csv_path: Path to CSV. Defaults to ``data/submissions.csv`` under the project root.

    Returns:
        DataFrame with normalized headers and canonical required column names.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is empty (no readable rows).
        pd.errors.ParserError: If the CSV cannot be parsed.
    """
    path = csv_path or CSV_FILE_PATH
    if not path.exists():
        msg = f"CSV file not found at: {path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decode failed for %s; retrying with latin-1", path)
        df = pd.read_csv(path, encoding="latin-1")
    except pd.errors.EmptyDataError as exc:
        msg = "CSV file is empty or could not be parsed."
        logger.error(msg)
        raise ValueError(msg) from exc
    except pd.errors.ParserError:
        logger.warning("CSV C-engine parse failed for %s; retrying with python engine", path)
        df = pd.read_csv(path, encoding="utf-8-sig", engine="python")

    df = canonicalize_submission_columns(df)

    if df.empty:
        msg = "CSV file contains no data rows."
        logger.error(msg)
        raise ValueError(msg)

    logger.info("Loaded %s rows from %s", len(df), path)
    return df


def load_submissions_from_bytes(data: bytes) -> pd.DataFrame:
    """
    Parse submission rows from an in-memory CSV (for example an HTTP upload).

    Raises:
        ValueError: If the buffer is empty or contains no data rows.
        pd.errors.ParserError: If the CSV cannot be parsed.
    """
    if not data or not data.strip():
        msg = "Uploaded CSV is empty."
        logger.error(msg)
        raise ValueError(msg)

    buffer = io.BytesIO(data)
    try:
        df = pd.read_csv(buffer, encoding="utf-8-sig")
    except UnicodeDecodeError:
        buffer.seek(0)
        df = pd.read_csv(buffer, encoding="latin-1")
    except pd.errors.EmptyDataError as exc:
        msg = "CSV file is empty or could not be parsed."
        logger.error(msg)
        raise ValueError(msg) from exc
    except pd.errors.ParserError:
        buffer.seek(0)
        logger.warning("CSV C-engine parse failed for upload; retrying with python engine")
        df = pd.read_csv(buffer, encoding="utf-8-sig", engine="python")

    df = canonicalize_submission_columns(df)

    if df.empty:
        msg = "CSV file contains no data rows."
        logger.error(msg)
        raise ValueError(msg)

    logger.info("Loaded %s rows from uploaded CSV bytes", len(df))
    return df


def preview_data(df: pd.DataFrame, rows: int = 5) -> None:
    """Print a concise preview of the dataset to stdout."""
    print("\nDataset Preview:")
    print(df.head(rows).to_string())
    print("\nColumns:")
    print(df.columns.tolist())
    print(f"\nTotal rows: {len(df)}")
