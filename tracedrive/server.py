"""Small loopback-only HTTP interface for the TraceDrive portfolio project."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .analysis import MAX_CSV_BYTES, THRESHOLDS, ValidationError
from .demo import sample_csv
from .store import RunNotFound, Store

ROOT = Path(__file__).resolve().parent.parent


class RequestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: Store, web_root: Path | None = None):
        if address[0] not in ("127.0.0.1", "localhost"):
            raise ValueError("TraceDrive serves only on loopback.")
        self.store = store
        self.web_root = (web_root or ROOT / "web").resolve()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server: Server

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def _respond(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict) -> None:
        self._respond(status, json.dumps(payload, allow_nan=False).encode(), "application/json; charset=utf-8")

    def _check_request_origin(self) -> None:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            raise RequestError(403, "invalid_host", "Use the localhost URL printed by the server.")
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            raise RequestError(403, "invalid_origin", "Open TraceDrive locally before sending requests.")

    def _body(self) -> dict:
        if self.headers.get("Transfer-Encoding"):
            raise RequestError(400, "invalid_body", "Chunked request bodies are not supported.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise RequestError(400, "invalid_body", "Content-Length must be a non-negative integer.") from None
        if length < 0:
            raise RequestError(400, "invalid_body", "Content-Length must be non-negative.")
        if length > MAX_CSV_BYTES:
            raise RequestError(413, "body_too_large", "Request exceeds the 2 MiB limit; upload a smaller CSV.")
        if length == 0:
            return {}
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise RequestError(415, "unsupported_media_type", "Send the request as application/json.")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestError(400, "invalid_body", "Request body is incomplete.")
        def invalid_constant(value: str) -> None:
            raise ValueError(f"Invalid JSON constant: {value}")
        try:
            body = json.loads(raw.decode("utf-8"), parse_constant=invalid_constant)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise RequestError(400, "invalid_json", "Request must contain valid UTF-8 JSON.") from None
        if not isinstance(body, dict):
            raise RequestError(400, "invalid_json", "The JSON body must be an object.")
        return body

    def _dispatch(self) -> None:
        self._check_request_origin()
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if self.command == "POST":
            body = self._body()
            if path == "/api/runs":
                if set(body) != {"name", "csv"}:
                    raise ValidationError("Provide exactly the name and csv fields.")
                self._json(201, {"run": self.server.store.add(body["name"], body["csv"])})
                return
            if path == "/api/demo/seed":
                if body:
                    raise ValidationError("The demo seed request must be an empty object.")
                self._json(200, self.server.store.seed())
                return
            raise RequestError(404, "not_found", "API route not found.")
        if self.command != "GET":
            raise RequestError(405, "method_not_allowed", "Only GET and POST are supported.")
        if path == "/api/state":
            self._json(200, {"runs": self.server.store.list_runs(), "thresholds": THRESHOLDS})
        elif path.startswith("/api/runs/"):
            self._json(200, self.server.store.get(path.removeprefix("/api/runs/")))
        elif path == "/api/compare":
            query = parse_qs(parsed.query)
            if set(query) != {"left", "right"} or any(len(values) != 1 for values in query.values()):
                raise ValidationError("Supply one left and one right run ID.")
            self._json(200, self.server.store.compare(query["left"][0], query["right"][0]))
        elif path == "/api/sample.csv":
            self._respond(200, sample_csv().encode(), "text/csv; charset=utf-8")
        elif path.startswith("/api/"):
            raise RequestError(404, "not_found", "API route not found.")
        else:
            relative = "index.html" if path == "/" else path.lstrip("/")
            file = (self.server.web_root / relative).resolve()
            if not file.is_relative_to(self.server.web_root) or not file.is_file():
                raise RequestError(404, "not_found", "Page or asset not found.")
            content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            self._respond(200, file.read_bytes(), content_type)

    def _handle(self) -> None:
        try:
            self._dispatch()
        except RequestError as exc:
            self._json(exc.status, {"error": exc.code, "message": str(exc)})
        except ValidationError as exc:
            self._json(400, {"error": "validation_error", "message": str(exc)})
        except RunNotFound as exc:
            self._json(404, {"error": "not_found", "message": str(exc)})
        except (TimeoutError, ConnectionError):
            self.close_connection = True
        except (sqlite3.Error, OSError):
            self.log_error("Storage or file operation failed")
            self._json(500, {"error": "storage_error", "message": "Local storage is unavailable. Check the database path and try again."})

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_DELETE = _handle
    do_OPTIONS = _handle
    do_PATCH = _handle


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TraceDrive locally.")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "tracedrive.sqlite3")
    args = parser.parse_args()
    server = Server(("127.0.0.1", args.port), Store(args.db))
    print(f"TraceDrive: http://127.0.0.1:{server.server_port}", flush=True)
    print("Local analysis only. Demo data are synthetic. Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TraceDrive.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
