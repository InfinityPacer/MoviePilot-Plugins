"""Temporary PR-Agent inline review probe.

This file is only used to validate the repository PR-Agent workflow on a
same-repository pull request and is not intended to be merged.
"""


def match_probe_event(expected_type: str, event: dict) -> bool:
    """Match a temporary probe event by type."""
    return event.get("type") == expected_type


def collect_probe_output(command: str) -> str:
    """Collect temporary probe output from a shell command."""
    import subprocess

    return subprocess.check_output(command, shell=True, text=True)
