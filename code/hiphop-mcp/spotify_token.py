"""Spotify access token management. Refreshes on demand, caches in-memory."""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

CFG_PATH = Path.home() / ".openclaw" / "spotify.json"
_cache = {"token": None, "expires_at": 0}


def _load_cfg():
    return json.loads(CFG_PATH.read_text())


def get_access_token():
    """Return a valid Spotify access token, refreshing if needed."""
    now = time.time()
    if _cache["token"] and _cache["expires_at"] - 60 > now:
        return _cache["token"]
    cfg = _load_cfg()
    if not cfg.get("refresh_token"):
        raise RuntimeError("No refresh_token. Run auth.py first.")
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": cfg["refresh_token"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        tok = json.loads(resp.read())
    _cache["token"] = tok["access_token"]
    _cache["expires_at"] = now + tok.get("expires_in", 3600)
    # Spotify sometimes rotates refresh_token
    if "refresh_token" in tok and tok["refresh_token"] != cfg["refresh_token"]:
        cfg["refresh_token"] = tok["refresh_token"]
        CFG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")
        CFG_PATH.chmod(0o600)
    return _cache["token"]
