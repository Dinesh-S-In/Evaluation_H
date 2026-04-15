"""Vercel Python serverless: POST /api/evaluate"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler

from src.http_evaluate import dispatch_evaluate

_CORS = (
    ("Access-Control-Allow-Origin", "*"),
    ("Access-Control-Allow-Methods", "POST, OPTIONS"),
    (
        "Access-Control-Allow-Headers",
        "Content-Type, X-Mock-Mode, X-OpenAI-Model",
    ),
)


class handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        for key, val in _CORS:
            self.send_header(key, val)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length > 0 else b""
        code, payload = dispatch_evaluate(body, self.headers)
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        for key, val in _CORS:
            self.send_header(key, val)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
