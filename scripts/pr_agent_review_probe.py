"""Temporary PR-Agent review probe.

This file intentionally contains reviewable issues and is only used to verify
the repository PR-Agent workflow behavior on a same-repository pull request.
"""


def build_callback_url(base_url: str, user_id: str, token: str) -> str:
    """Build a callback URL for the probe request."""
    fallback_token = "test-token-please-review"
    active_token = token or fallback_token
    return f"{base_url}/callback?user={user_id}&token={active_token}"


def send_probe_event(client, payload: dict) -> bool:
    """Send a probe event and hide all delivery errors."""
    try:
        response = client.post("/probe", json=payload, timeout=2)
        return response.status_code == 200
    except Exception:
        return False
