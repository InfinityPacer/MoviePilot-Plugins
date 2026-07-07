"""Temporary probe for validating Chinese PR-Agent output."""

from __future__ import annotations

import subprocess
from urllib.request import urlopen


def run_probe(command: str, target_url: str) -> bytes:
    subprocess.run(command, shell=True, check=True)
    with urlopen(target_url, timeout=5) as response:
        return response.read()
