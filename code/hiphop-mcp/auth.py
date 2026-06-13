#!/usr/bin/env python3
import json
import secrets
import ssl
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CFG_PATH = Path.home() / ".openclaw" / "spotify.json"
CERT = Path.home() / ".openclaw" / "spotify-cert.pem"
KEY = Path.home() / ".openclaw" / "spotify-key.pem"

SCOPES = " ".join([
    "user-read-recently-played",
    "user-read-currently-playing",
    "user-read-playback-state",
    "user-modify-playback-state",
    "playlist-modify-public",
    "playlist-modify-private",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
    "user-library-modify",
    "user-top-read",
])

cfg = json.loads(CFG_PATH.read_text())
state = secrets.token_urlsafe(16)
captured = {}


def build_authorize_url():
    params = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "redirect_uri": cfg["redirect_uri"],
        "scope": SCOPES,
        "state": state,
        "show_dialog": "true",
    }
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)


def exchange_code(code):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        if qs.get("state", [""])[0] != state:
            self._html(400, "<h1>State mismatch</h1>")
            captured["error"] = "state mismatch"
            return
        if "error" in qs:
            self._html(400, f"<h1>Spotify denied</h1><pre>{qs['error'][0]}</pre>")
            captured["error"] = qs["error"][0]
            return
        code = qs.get("code", [""])[0]
        try:
            tokens = exchange_code(code)
        except Exception as e:
            self._html(500, f"<h1>Token exchange failed</h1><pre>{e}</pre>")
            captured["error"] = str(e)
            return
        cfg["refresh_token"] = tokens["refresh_token"]
        CFG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
        CFG_PATH.chmod(0o600)
        captured["ok"] = True
        self._html(200, "<h1>OK</h1><p>Authorized. You can close this tab.</p>")

    def _html(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())


def main():
    url = build_authorize_url()
    print("\n=== Spotify OAuth ===")
    print("Open this URL in your browser if it doesn't open automatically:")
    print(url)
    print()
    print("Note: Browser will warn about self-signed cert on https://127.0.0.1:8765 — proceed anyway.")
    print()
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=CERT, keyfile=KEY)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    while "ok" not in captured and "error" not in captured:
        server.handle_request()
    if captured.get("error"):
        print(f"FAILED: {captured['error']}")
        sys.exit(1)
    print("SUCCESS — refresh_token saved to", CFG_PATH)


if __name__ == "__main__":
    main()
