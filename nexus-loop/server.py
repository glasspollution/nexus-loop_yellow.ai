#!/usr/bin/env python
"""The manager screen's live, approval-gated backend.

    python server.py --kit ../kit --out out/practice --port 8765 --replay-url http://127.0.0.1:8719

Endpoints (JSON; same-origin only, including the Vite development proxy):
  GET  /api/health                 {"ok": true, ...}
  GET  /api/screen                 current in-memory screen model
  GET  /api/report                 current in-memory report
  GET  /api/report/generated       fresh detect/diagnose/prescribe output before decisions
  GET  /api/definitions            the definitions registry
  GET  /api/decisions              decisions in this server session, oldest first
  POST /api/decisions              {"prescription_id" | "fix_id", "verdict": accepted|rejected|deferred,
                                    "decided_by", "reason", "proposal_sha", "generated_report_sha256"}
                                   -> approve runs replay live; reject/defer do not; returns {"result", "screen"}
Anything else is served from --static (the built website), falling back to index.html.

The corpus analysis runs in a background thread.  No request writes a report,
screen, decision log, replay cache or replay ledger: all review state disappears
when this process exits.  The batch run.py path remains available for producing
submission artifacts separately.
"""
import argparse
import json
import mimetypes
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from nexus import decisions  # noqa: E402
from nexus.live_session import LiveSession  # noqa: E402

MAX_BODY = 64 * 1024


class ScreenHTTPServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind a port that is already in
    # use, so a stale server keeps answering with its old session state.  Claim the
    # port exclusively there so a duplicate launch fails loudly instead.
    if os.name == "nt":
        allow_reuse_address = False

        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()


def make_handler(out_dir, static_dir, workflow, kit_dir=None, wait_timeout=30):
    class Handler(BaseHTTPRequestHandler):
        server_version = "nexus-loop/1"

        def _send(self, status, obj):
            body = json.dumps(obj, indent=1).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            return self._send(405, {"error": "cross-origin requests are not supported; use the same-origin API"})

        def do_GET(self):
            path = urlparse(self.path).path.rstrip("/") or "/"
            if path == "/api/health":
                health = workflow.health()
                health.update({"ok": True, "mode": "live-session", "out_dir": out_dir,
                               "kit_dir": os.path.abspath(kit_dir) if kit_dir else None,
                               "replay_configured": bool(workflow.replay_url)})
                return self._send(200, health)
            if path == "/api/screen":
                return self._workflow_response(workflow.screen)
            if path in ("/api/report", "/api/report/generated"):
                return self._workflow_response(lambda timeout: workflow.report(
                    generated=path.endswith("/generated"), timeout=timeout))
            if path == "/api/definitions":
                return self._workflow_response(lambda timeout: workflow.report(timeout=timeout).get("definitions", []))
            if path == "/api/decisions":
                return self._workflow_response(workflow.events)
            return self._static(path)

        def _workflow_response(self, operation):
            try:
                return self._send(200, operation(timeout=wait_timeout))
            except decisions.DecisionError as exc:
                return self._send(exc.status, {"error": exc.message, "analysis_state": workflow.state})

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            if path != "/api/decisions":
                return self._send(404, {"error": "not found"})
            lengths = self.headers.get_all("Content-Length") or []
            if len(lengths) != 1:
                return self._send(411 if not lengths else 400, {"error": "one valid Content-Length is required"})
            raw_length = lengths[0].strip()
            if not raw_length.isascii() or not raw_length.isdecimal():
                return self._send(400, {"error": "malformed Content-Length"})
            normalised_length = raw_length.lstrip("0") or "0"
            limit = str(MAX_BODY)
            if len(normalised_length) > len(limit) or \
                    (len(normalised_length) == len(limit) and normalised_length > limit):
                return self._send(413, {"error": "request too large"})
            n = int(normalised_length)
            try:
                body = json.loads(self.rfile.read(n))
            except ValueError as exc:
                return self._send(400, {"error": "bad json: %s" % exc})
            if not isinstance(body, dict):
                return self._send(400, {"error": "request body must be a JSON object"})
            if not isinstance(body.get("proposal_sha"), str) or not body["proposal_sha"].strip():
                return self._send(400, {"error": "proposal_sha is required; reload the proposal before deciding"})
            if not isinstance(body.get("generated_report_sha256"), str) or not body["generated_report_sha256"].strip():
                return self._send(400, {"error": "generated_report_sha256 is required; reload before deciding"})
            try:
                result, refreshed = workflow.decide(
                    body.get("prescription_id") or body.get("fix_id") or "",
                    body.get("verdict"), body.get("decided_by"), body.get("reason"),
                    seen_session_sha=body.get("generated_report_sha256"),
                    seen_proposal_sha=body.get("proposal_sha"), timeout=wait_timeout)
            except decisions.DecisionError as exc:
                return self._send(exc.status, {"error": exc.message})
            return self._send(200, {"result": result, "screen": refreshed})

        def _static(self, path):
            if not static_dir or not os.path.isdir(static_dir):
                return self._send(404, {"error": "no website built yet; the API is under /api/",
                                        "endpoints": ["/api/health", "/api/screen", "/api/report", "/api/report/generated",
                                                      "/api/definitions", "/api/decisions"]})
            root = os.path.realpath(os.path.abspath(static_dir))
            rel = os.path.normpath(path.lstrip("/")) if path != "/" else "index.html"
            full = os.path.realpath(os.path.join(root, rel))
            try:
                contained = os.path.commonpath((root, full)) == root
            except ValueError:
                contained = False
            if not contained or not os.path.isfile(full):
                full = os.path.join(root, "index.html")
                if not os.path.isfile(full):
                    return self._send(404, {"error": "not found"})
            with open(full, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):
            pass

    return Handler


def _load_saved_report(out_dir):
    for name in (decisions.GENERATED, decisions.REPORT):
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
    return None


def serve(out_dir, host="127.0.0.1", port=8765, static_dir=None, kit_dir=None, cache_dir=None,
          replay_url=None, replay_team=None, team="nexus-loop", workflow=None, wait_timeout=30):
    out_dir = os.path.abspath(out_dir)
    if workflow is None:
        workflow = LiveSession(replay_url=replay_url, replay_team=replay_team)
        if kit_dir:
            workflow.start_analysis(os.path.abspath(kit_dir), cache_dir=cache_dir, team=team)
        else:
            saved = _load_saved_report(out_dir)
            if saved is not None:
                workflow = LiveSession.from_report(saved, replay_url=replay_url, replay_team=replay_team)
    httpd = ScreenHTTPServer((host, port), make_handler(out_dir, static_dir, workflow, kit_dir, wait_timeout))
    httpd.live_session = workflow
    return httpd


def main(argv=None):
    ap = argparse.ArgumentParser(description="Nexus Loop screen backend")
    ap.add_argument("--out", default=os.path.join(ROOT, "out"), help="run.py output directory")
    ap.add_argument("--kit", default=os.path.join(ROOT, "..", "kit"),
                    help="source kit to analyse live (default: the workspace's original kit)")
    ap.add_argument("--cache-dir", default=os.path.join(ROOT, ".cache"),
                    help="read-through corpus loader cache; no review outcomes are stored here")
    ap.add_argument("--team", default="nexus-loop")
    ap.add_argument("--replay-url", default=os.environ.get("NEXUS_REPLAY_URL"),
                    help="live replay engine base URL; required to produce an outcome after approval")
    ap.add_argument("--replay-team", default=os.environ.get("NEXUS_REPLAY_TEAM"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--static", default=os.path.join(ROOT, "screen", "dist"), help="built website directory")
    a = ap.parse_args(argv)
    httpd = serve(a.out, a.host, a.port, a.static, kit_dir=a.kit, cache_dir=a.cache_dir,
                  replay_url=a.replay_url, replay_team=a.replay_team, team=a.team)
    print("nexus-loop live screen backend on http://%s:%d  (kit: %s)" %
          (a.host, a.port, os.path.abspath(a.kit)))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
