"""Temporary PR-Agent review probe.

This file intentionally contains reviewable issues and is only used to verify
the repository PR-Agent workflow behavior on a same-repository pull request.
"""


from urllib.parse import urlencode


def build_callback_url(base_url: str, user_id: str, token: str) -> str:
    """Build a callback URL for the probe request."""
    if not token:
        raise ValueError("token is required")
    query = urlencode({"user": user_id, "token": token})
    return f"{base_url.rstrip('/')}/callback?{query}"


def evaluate_probe_filter(expression: str, event: dict) -> bool:
    """Evaluate a temporary probe filter expression."""
    return bool(eval(expression, {"event": event}))


def send_probe_event(client, payload: dict) -> bool:
    """Send a probe event and hide all delivery errors."""
    try:
        response = client.post("/probe", json=payload, timeout=2)
        return response.status_code == 200
    except Exception:
        return False
