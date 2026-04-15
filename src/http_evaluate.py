"""Vercel / HTTP entry logic for POST /api/evaluate (JSON or raw CSV body)."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv

from src.load_data import load_submissions_from_bytes
from src.pipeline import run_evaluation_ranking

logger = logging.getLogger(__name__)


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _lower_headers(headers: Any) -> dict[str, str]:
    if hasattr(headers, "items"):
        return {str(k).lower(): str(v) for k, v in headers.items()}
    return {}


def dispatch_evaluate(body: bytes, headers: Any) -> tuple[int, dict[str, Any]]:
    """
    Run evaluation + ranking on an uploaded CSV.

    Supports:
        - ``application/json`` with ``{ "csv_base64": "...", "mock"?: bool, "model"?: str }``
        - ``text/csv`` (or ``application/csv``) raw body; optional ``X-Mock-Mode`` and ``X-OpenAI-Model`` headers.
    """
    load_dotenv()
    h = _lower_headers(headers)

    if not body:
        return 400, {"error": "Empty request body"}

    ct = (h.get("content-type") or "").split(";")[0].strip().lower()

    try:
        if ct in {"text/csv", "application/csv"}:
            df = load_submissions_from_bytes(body)
            mock = _truthy(h.get("x-mock-mode")) or _truthy(os.getenv("MOCK_EVALUATION"))
            model_hdr = (h.get("x-openai-model") or "").strip()
            model = model_hdr or (os.getenv("OPENAI_MODEL") or "").strip() or None
        else:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                return 400, {"error": "JSON body must be an object"}

            b64 = data.get("csv_base64")
            if not isinstance(b64, str) or not b64.strip():
                return 400, {"error": "Missing or invalid csv_base64"}

            try:
                raw = base64.b64decode(b64, validate=True)
            except binascii.Error:
                return 400, {"error": "csv_base64 is not valid base64"}

            df = load_submissions_from_bytes(raw)

            mock_val = data.get("mock")
            if mock_val is None:
                mock = _truthy(os.getenv("MOCK_EVALUATION"))
            elif isinstance(mock_val, bool):
                mock = mock_val
            else:
                mock = bool(mock_val)

            model_val = data.get("model")
            if isinstance(model_val, str) and model_val.strip():
                model = model_val.strip()
            else:
                model = (os.getenv("OPENAI_MODEL") or "").strip() or None

        ranked = run_evaluation_ranking(df, mock=mock, model=model)
        payload = [r.model_dump(mode="json") for r in ranked]
        return 200, {"results": payload, "count": len(payload)}

    except json.JSONDecodeError as exc:
        return 400, {"error": "Invalid JSON", "detail": str(exc)}
    except ValueError as exc:
        logger.info("Validation error in evaluate: %s", exc)
        return 400, {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Evaluate failed")
        return 500, {"error": "Evaluation failed", "detail": str(exc)}
