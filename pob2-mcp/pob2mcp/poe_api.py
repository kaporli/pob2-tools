"""GGG OAuth (PKCE, client_id=pob — same flow Path of Building 2 uses) and
character endpoints of api.pathofexile.com."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser

import requests

AUTH_URL = "https://www.pathofexile.com/oauth/authorize"
TOKEN_URL = "https://www.pathofexile.com/oauth/token"
API_BASE = "https://api.pathofexile.com"
CLIENT_ID = "pob"
SCOPES = ["account:profile", "account:leagues", "account:characters", "account:trade"]
# The "pob" OAuth client is registered for these localhost ports (see LaunchServer.lua)
REDIRECT_PORTS = [49082, 49083, 49084]

USER_AGENT = "pob2-mcp/0.1 (Path of Building 2 headless MCP bridge)"

TOKEN_CACHE = os.path.join(os.path.expanduser("~"), ".pob2-mcp", "token.json")


class PoeApiError(RuntimeError):
    pass


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        _CallbackHandler.result = params
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if "code" in params:
            self.wfile.write(b"<h1>pob2-mcp: authentication successful.</h1>You can close this tab.")
        else:
            self.wfile.write(b"<h1>pob2-mcp: authentication failed.</h1>")

    def log_message(self, *a):
        pass


class PoeApi:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self._token: dict = {}
        self._load_token()

    # -- token management -----------------------------------------------------

    def _load_token(self):
        try:
            with open(TOKEN_CACHE, "r", encoding="utf-8") as f:
                self._token = json.load(f)
        except (OSError, ValueError):
            self._token = {}

    def _save_token(self):
        os.makedirs(os.path.dirname(TOKEN_CACHE), exist_ok=True)
        with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
            json.dump(self._token, f)

    def _store_token_response(self, data: dict):
        self._token = {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_at": time.time() + data.get("expires_in", 3600),
        }
        self._save_token()

    def authenticate(self, timeout: int = 180) -> str:
        """Interactive PKCE flow: opens the user's browser, waits for redirect."""
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        state = secrets.token_hex(8)

        server = None
        port = None
        for p in REDIRECT_PORTS:
            try:
                server = http.server.HTTPServer(("localhost", p), _CallbackHandler)
                port = p
                break
            except OSError:
                continue
        if server is None:
            raise PoeApiError("could not bind any of ports 49082-49084 for the OAuth redirect")

        redirect_uri = f"http://localhost:{port}"
        auth_url = (
            f"{AUTH_URL}?client_id={CLIENT_ID}&response_type=code"
            f"&scope={'%20'.join(SCOPES)}&state={state}"
            f"&code_challenge={challenge}&code_challenge_method=S256"
            f"&redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
        )

        _CallbackHandler.result = {}
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        webbrowser.open(auth_url)
        thread.join(timeout)
        server.server_close()

        params = _CallbackHandler.result
        if not params:
            raise PoeApiError(
                f"No OAuth redirect received within {timeout}s. "
                f"Open this URL manually and approve access: {auth_url}"
            )
        if params.get("state") != state:
            raise PoeApiError("OAuth state mismatch")
        if "code" not in params:
            raise PoeApiError(f"OAuth error: {params.get('error')}: {params.get('error_description')}")

        resp = self.session.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "authorization_code",
                "code": params["code"],
                "redirect_uri": redirect_uri,
                "scope": " ".join(SCOPES),
                "code_verifier": verifier,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise PoeApiError(f"token exchange failed ({resp.status_code}): {resp.text[:300]}")
        self._store_token_response(resp.json())
        return "authenticated"

    def _refresh(self):
        if not self._token.get("refresh_token"):
            raise PoeApiError("not authenticated — call authenticate() first")
        resp = self.session.post(
            TOKEN_URL,
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self._token["refresh_token"],
            },
            timeout=30,
        )
        if resp.status_code != 200:
            self._token = {}
            self._save_token()
            raise PoeApiError(
                f"token refresh failed ({resp.status_code}); re-run authenticate()"
            )
        self._store_token_response(resp.json())

    def _auth_header(self) -> dict:
        if not self._token.get("access_token"):
            raise PoeApiError("not authenticated — call authenticate() first")
        if time.time() >= self._token.get("expires_at", 0):
            self._refresh()
        return {"Authorization": f"Bearer {self._token['access_token']}"}

    @property
    def is_authenticated(self) -> bool:
        return bool(self._token.get("access_token"))

    # -- endpoints ------------------------------------------------------------

    def _get(self, endpoint: str) -> dict:
        resp = self.session.get(API_BASE + endpoint, headers=self._auth_header(), timeout=30)
        if resp.status_code == 401:
            self._refresh()
            resp = self.session.get(API_BASE + endpoint, headers=self._auth_header(), timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "10"))
            time.sleep(min(wait, 60))
            resp = self.session.get(API_BASE + endpoint, headers=self._auth_header(), timeout=30)
        if resp.status_code != 200:
            raise PoeApiError(f"GET {endpoint} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def list_characters(self, realm: str = "poe2") -> list[dict]:
        path = "/character" if realm == "pc" else f"/character/{realm}"
        return self._get(path).get("characters", [])

    def get_character(self, name: str, realm: str = "poe2") -> dict:
        path = ("/character" if realm == "pc" else f"/character/{realm}") + "/" + urllib.parse.quote(name)
        data = self._get(path)
        char = data.get("character")
        if not char:
            raise PoeApiError(f"character {name!r} not found in response")
        return char
