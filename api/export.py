"""Vercel Python serverless: POST /api/export"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from src.http_export import dispatch_export

_CORS = (
    ("Access-Control-Allow-Origin", "*"),
    ("Access-Control-Allow-Methods", "POST, OPTIONS"),
    ("Access-Control-Allow-Headers", "Content-Type"),
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
        code, blob, ctype, extra = dispatch_export(body)
        self.send_response(code)
        for key, val in _CORS:
            self.send_header(key, val)
        self.send_header("Content-Type", ctype)
        for key, val in extra:
            self.send_header(key, val)
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)
