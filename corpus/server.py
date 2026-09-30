"""Serve one independently retained collection on loopback, without network acquisition."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .query import select_rows
from .reader import Collection


def make_server(bundle, state, port=8768):
    collection = Collection(bundle, state)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, content, mime="application/json; charset=utf-8", filename=None):
            data = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", 'attachment; filename="' + filename + '"')
            self.end_headers()
            self.wfile.write(data)

        def permitted(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            return self.headers.get("Host") == expected and (not origin or origin == "http://" + expected)

        def do_GET(self):
            if not self.permitted():
                return self.reply(403, {"error": "Use this collection's loopback address"})
            url = urlsplit(self.path)
            params = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    return self.reply(200, Path(__file__).with_name("app.html").read_bytes(), "text/html; charset=utf-8")
                if url.path == "/api/collection":
                    return self.reply(200, collection.overview())
                if url.path == "/api/query":
                    filters = {k: params.get(k) or None for k in ("kind", "hardware", "model", "engine", "scenario", "unit")}
                    result = select_rows(collection.db, **filters, limit=min(int(params.get("limit", 25)), 100), offset=int(params.get("offset", 0)))
                    return self.reply(200, result)
                if url.path == "/api/history":
                    return self.reply(200, collection.history(params.get("row_id", "")))
                if url.path == "/api/export":
                    path = collection.export(params.get("row_id", ""), params.get("attempt"))
                    return self.reply(200, path.read_bytes(), filename=path.name)
                return self.reply(404, {"error": "Unknown collection route"})
            except (ValueError, KeyError, FileNotFoundError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception as exc:
                self.log_error("Collection read failed: %s", exc)
                self.reply(500, {"error": "Could not read the retained collection: " + str(exc)})

        def do_POST(self):
            if not self.permitted():
                return self.reply(403, {"error": "Cross-origin operations are not allowed"})
            if self.path != "/api/reproject":
                return self.reply(404, {"error": "Unknown collection operation"})
            try:
                if self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Expected application/json")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid request size")
                body = json.loads(self.rfile.read(size))
                result = collection.attempt(body.get("row_id", ""), body.get("actor", ""))
                self.reply(201, result)
            except (ValueError, KeyError, FileNotFoundError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception as exc:
                self.log_error("Projection attempt failed: %s", exc)
                self.reply(500, {"error": "Attempt was not completed: " + str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    server = make_server(args.bundle, args.state, args.port)
    print(f"Cantos collection: http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
