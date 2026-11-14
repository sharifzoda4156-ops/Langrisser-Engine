"""Loopback-only development stand. No production authentication or hosting."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from urllib.parse import parse_qs, urlsplit

from .errors import Conflict, EngineError, NotFound
from .stand import Stand
from .game import RULESET, supported_rulesets

MAX_BODY = 1024 * 1024


def make_server(database, port=8765):
    stand = Stand(database)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Do not print request bodies or model data.

        def send_json(self, status, data):
            body = (json.dumps(data, sort_keys=True) + "\n").encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def route(self, method):
            try:
                # Reject browser-originated cross-site requests and DNS rebinding.
                expected_host = f"127.0.0.1:{self.server.server_port}"
                if self.headers.get("Host") != expected_host or self.headers.get("Origin"):
                    self.send_json(403, {"error": "loopback machine-client interface only"})
                    return
                parts = urlsplit(self.path)
                if method == "GET" and parts.path == "/health":
                    self.send_json(200, {"status": "ok", "protocol_version": 1,
                                         "fidelity": "synthetic_fixture", "default_ruleset": RULESET,
                                         "supported_rulesets": supported_rulesets()})
                    return
                payload = None
                if method == "POST":
                    length = int(self.headers.get("Content-Length", "-1"))
                    if not 0 < length <= MAX_BODY:
                        self.send_json(413, {"error": "body must be 1..1048576 bytes"})
                        return
                    if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                        self.send_json(415, {"error": "application/json required"})
                        return
                    payload = json.loads(self.rfile.read(length))
                if method == "POST" and parts.path == "/matches":
                    self.send_json(201, stand.create_match(payload))
                    return
                match = re.fullmatch(r"/matches/([0-9a-f]{32})/(request|actions|replay)", parts.path)
                if match:
                    match_id, endpoint = match.groups()
                    if method == "GET" and endpoint == "request":
                        query = parse_qs(parts.query)
                        if set(query) != {"player"} or len(query["player"]) != 1:
                            raise EngineError("exactly one player query parameter required")
                        self.send_json(200, stand.get_decision_request(match_id, int(query["player"][0])))
                        return
                    if method == "GET" and endpoint == "replay":
                        self.send_json(200, stand.get_replay(match_id))
                        return
                    if method == "POST" and endpoint == "actions":
                        self.send_json(200, stand.submit_action(match_id, payload))
                        return
                self.send_json(404, {"error": "route not found"})
            except NotFound as error:
                self.send_json(404, {"error": str(error)})
            except Conflict as error:
                self.send_json(409, {"error": str(error)})
            except (EngineError, ValueError, TypeError) as error:
                self.send_json(400, {"error": str(error)})

        def do_GET(self):
            self.route("GET")

        def do_POST(self):
            self.route("POST")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
