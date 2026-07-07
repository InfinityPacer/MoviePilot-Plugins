"""Temporary PR-Agent inline review probe.

This file is only used to validate the repository PR-Agent workflow on a
same-repository pull request and is not intended to be merged.
"""


def evaluate_probe_expression(expression: str, event: dict) -> bool:
    """Evaluate a temporary probe expression."""
    return bool(eval(expression, {"event": event}))
