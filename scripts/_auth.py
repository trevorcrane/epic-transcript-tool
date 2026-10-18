"""Shared API-token header for scripts that call guarded Transcript Machine routes.

The token comes from the environment only (TRANSCRIPT_API_TOKEN, loaded by the
caller with `set -a; . .env; set +a`). It is never printed or written to evidence.
"""
from __future__ import annotations

import os


def api_token() -> str:
    return (os.getenv("TRANSCRIPT_API_TOKEN") or "").strip()


def auth_headers() -> dict[str, str]:
    token = api_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def redact(text: str) -> str:
    token = api_token()
    return text.replace(token, "[redacted]") if token and isinstance(text, str) else text
