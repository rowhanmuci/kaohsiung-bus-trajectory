"""Minimal TDX (Transport Data eXchange) API client.

Credentials are read from the project-root .env (TDX_CLIENT_ID / TDX_CLIENT_SECRET)
and are never printed. Basic members may call the API 5 times per minute per key,
so consecutive requests are spaced at least MIN_INTERVAL seconds apart.
"""
import time
from pathlib import Path
import os

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
BASE_URL = "https://tdx.transportdata.tw/api/basic"
MIN_INTERVAL = 12.5  # seconds between calls -> stays under 5 calls/min


class TDX:
    def __init__(self):
        self.session = requests.Session()
        self._token = None
        self._token_expiry = 0.0
        self._last_call = 0.0

    def _access_token(self):
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = self.session.post(TOKEN_URL, timeout=30, data={
            "grant_type": "client_credentials",
            "client_id": os.environ["TDX_CLIENT_ID"],
            "client_secret": os.environ["TDX_CLIENT_SECRET"],
        })
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + payload.get("expires_in", 3600)
        return self._token

    def get(self, path, **params):
        """GET BASE_URL + path and return the decoded JSON body."""
        wait = MIN_INTERVAL - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        params.setdefault("$format", "JSON")
        resp = self.session.get(
            BASE_URL + path, params=params, timeout=60,
            headers={"Authorization": f"Bearer {self._access_token()}", "Accept-Encoding": "gzip"},
        )
        self._last_call = time.time()
        resp.raise_for_status()
        return resp.json()
