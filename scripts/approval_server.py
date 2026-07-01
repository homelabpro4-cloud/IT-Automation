#!/usr/bin/env python3
"""
Lightweight approval callback server.

Ansible playbooks POST to this server to send approval requests and poll for answers.
Teams/Email contain unique links that hit /approve or /deny with a token.

Run this as a service on your Semaphore host:
  python3 approval_server.py

Environment variables:
  APPROVAL_HOST      - bind host (default: 0.0.0.0)
  APPROVAL_PORT      - bind port (default: 5050)
  APPROVAL_SECRET    - HMAC secret for token validation
  PUBLIC_URL         - public URL reachable from Teams/Email (e.g. https://automation.example.com)
"""

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SECRET = os.environ.get("APPROVAL_SECRET", "change-me-in-production")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:5050")
APPROVAL_TTL = int(os.environ.get("APPROVAL_TTL_SECONDS", "3600"))

# In-memory store: token -> {status, created_at, context}
_store: dict = {}
_lock = Lock()


def generate_token(context: dict) -> str:
    token = str(uuid.uuid4())
    with _lock:
        _store[token] = {
            "status": "pending",
            "created_at": time.time(),
            "context": context,
        }
    return token


def make_signed_url(action: str, token: str) -> str:
    sig = hmac.new(SECRET.encode(), f"{action}:{token}".encode(), hashlib.sha256).hexdigest()
    return f"{PUBLIC_URL}/{action}?token={token}&sig={sig}"


def verify_sig(action: str, token: str, sig: str) -> bool:
    expected = hmac.new(SECRET.encode(), f"{action}:{token}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def get_approval_links(context: dict) -> dict:
    token = generate_token(context)
    return {
        "token": token,
        "approve_url": make_signed_url("approve", token),
        "deny_url": make_signed_url("deny", token),
    }


def get_status(token: str) -> dict:
    with _lock:
        entry = _store.get(token)
    if not entry:
        return {"status": "not_found"}
    if time.time() - entry["created_at"] > APPROVAL_TTL:
        return {"status": "expired"}
    return {"status": entry["status"], "context": entry["context"]}


def set_status(token: str, status: str) -> bool:
    with _lock:
        if token not in _store:
            return False
        _store[token]["status"] = status
        _store[token]["resolved_at"] = time.time()
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_action(self, action: str):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get("token", [None])[0]
        sig = params.get("sig", [None])[0]

        if not token or not sig:
            self._send_html(400, "<h2>Bad request: missing token or signature.</h2>")
            return

        if not verify_sig(action, token, sig):
            self._send_html(403, "<h2>Invalid or tampered link.</h2>")
            return

        current = get_status(token)
        if current["status"] == "expired":
            self._send_html(410, "<h2>This approval link has expired.</h2>")
            return
        if current["status"] not in ("pending",):
            self._send_html(200, f"<h2>Already {current['status']}. No further action needed.</h2>")
            return

        set_status(token, action + "d")  # approved / denied
        colour = "#28a745" if action == "approve" else "#dc3545"
        word = "APPROVED" if action == "approve" else "DENIED"
        ctx = current.get("context", {})
        self._send_html(
            200,
            f"""<html><body style="font-family:sans-serif;text-align:center;padding:40px">
            <h1 style="color:{colour}">Action {word}</h1>
            <p>Host: <strong>{ctx.get('alert_host','N/A')}</strong></p>
            <p>Alert: {ctx.get('alert_trigger','N/A')}</p>
            <p>The automation will proceed accordingly. You may close this tab.</p>
            </body></html>""",
        )

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/approve":
            self._handle_action("approve")
        elif path == "/deny":
            self._handle_action("deny")
        elif path == "/status":
            params = parse_qs(parsed.query)
            token = params.get("token", [None])[0]
            if not token:
                self._send_json(400, {"error": "missing token"})
                return
            self._send_json(200, get_status(token))
        elif path == "/health":
            self._send_json(200, {"status": "ok", "pending": sum(1 for v in _store.values() if v["status"] == "pending")})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/request":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            links = get_approval_links(body)
            self._send_json(200, links)
        else:
            self._send_json(404, {"error": "not found"})


def main():
    host = os.environ.get("APPROVAL_HOST", "0.0.0.0")
    port = int(os.environ.get("APPROVAL_PORT", "5050"))
    server = HTTPServer((host, port), Handler)
    log.info("Approval server listening on %s:%s", host, port)
    server.serve_forever()


if __name__ == "__main__":
    main()
