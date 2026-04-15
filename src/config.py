"""Centralized configuration and filesystem paths for the hackathon evaluator."""

from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BASE_DIR / "data"
OUTPUT_DIR: Path = BASE_DIR / "output"
PROMPTS_DIR: Path = BASE_DIR / "prompts"

CSV_FILE_PATH: Path = DATA_DIR / "submissions.csv"
SYSTEM_PROMPT_PATH: Path = PROMPTS_DIR / "system_prompt.txt"
EVALUATION_PROMPT_PATH: Path = PROMPTS_DIR / "evaluation_prompt.txt"

FULL_RESULTS_CSV: Path = OUTPUT_DIR / "full_results.csv"
FULL_RESULTS_XLSX: Path = OUTPUT_DIR / "full_results.xlsx"
TOP10_CSV: Path = OUTPUT_DIR / "top10_shortlist.csv"
TOP10_XLSX: Path = OUTPUT_DIR / "top10_shortlist.xlsx"
FINAL_SHORTLIST_CSV: Path = OUTPUT_DIR / "final_shortlist.csv"
SESSION_RESULTS_JSON: Path = OUTPUT_DIR / "session_results.json"


def ensure_output_dir() -> None:
    """Create the output directory before writing exports or session files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
