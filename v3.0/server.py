from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import error as SocketError
from urllib.parse import parse_qs, urlparse

from src.engine import run_query


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/query":
            query = parse_qs(parsed.query)
            question = query.get("q", [""])[0].strip()
            session_id = query.get("session_id", ["default"])[0].strip() or "default"
            if not question:
                self.send_json({"error": "missing query parameter: q"}, 400)
                return
            try:
                self.send_json(run_query(question, session_id=session_id))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "app": "FinSafe-QA V3.0"})
            return
        return super().do_GET()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    server = None
    for candidate_port in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate_port), Handler)
            port = candidate_port
            break
        except OSError as exc:
            if exc.errno != 48:
                raise
    if server is None:
        raise SocketError(f"No available port found from {port} to {port + 19}")
    print(f"FinSafe-QA V3.0 running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
