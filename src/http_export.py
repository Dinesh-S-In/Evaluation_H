"""Vercel / HTTP entry logic for POST /api/export (build CSV or XLSX from ranked JSON)."""

from __future__ import annotations

import json
import logging
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

from src.exporter import (
    build_results_dataframe,
    export_dataframe_to_csv_bytes,
    export_dataframe_to_excel_bytes,
)
from src.models import RankedEvaluation

logger = logging.getLogger(__name__)


def dispatch_export(body: bytes) -> tuple[int, bytes, str, list[tuple[str, str]]]:
    """
    Build an export file from a prior ``/api/evaluate`` payload.

    Request JSON:
        ``{ "results": [...], "format": "csv"|"xlsx", "scope": "full"|"top10" }``
    """
    load_dotenv()

    extra: list[tuple[str, str]] = []

    if not body:
        return _json_response(400, {"error": "Empty request body"}, extra)

    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        return _json_response(400, {"error": "Invalid JSON", "detail": str(exc)}, extra)

    if not isinstance(data, dict):
        return _json_response(400, {"error": "JSON body must be an object"}, extra)

    results_raw = data.get("results")
    if not isinstance(results_raw, list):
        return _json_response(400, {"error": "results must be a list"}, extra)

    fmt = str(data.get("format", "csv")).lower().strip()
    scope = str(data.get("scope", "full")).lower().strip()
    if scope not in {"full", "top10"}:
        return _json_response(400, {"error": "scope must be full or top10"}, extra)
    if fmt not in {"csv", "xlsx"}:
        return _json_response(400, {"error": "format must be csv or xlsx"}, extra)

    ranked: list[RankedEvaluation] = []
    for idx, item in enumerate(results_raw):
        if not isinstance(item, dict):
            return _json_response(400, {"error": f"results[{idx}] must be an object"}, extra)
        try:
            ranked.append(RankedEvaluation.model_validate(item))
        except ValidationError as exc:
            return _json_response(
                400,
                {"error": f"Invalid results[{idx}]", "detail": exc.json()},
                extra,
            )

    if scope == "top10":
        ranked_out = [r for r in ranked if r.shortlisted]
    else:
        ranked_out = ranked

    df = build_results_dataframe(ranked_out)

    if fmt == "xlsx":
        blob = export_dataframe_to_excel_bytes(df)
        ctype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "top10_shortlist.xlsx" if scope == "top10" else "full_results.xlsx"
    else:
        blob = export_dataframe_to_csv_bytes(df)
        ctype = "text/csv; charset=utf-8"
        filename = "top10_shortlist.csv" if scope == "top10" else "full_results.csv"

    extra.append(("Content-Disposition", f'attachment; filename="{filename}"'))
    return 200, blob, ctype, extra


def _json_response(
    code: int,
    obj: dict[str, Any],
    extra: list[tuple[str, str]],
) -> tuple[int, bytes, str, list[tuple[str, str]]]:
    payload = json.dumps(obj).encode("utf-8")
    return code, payload, "application/json; charset=utf-8", extra
