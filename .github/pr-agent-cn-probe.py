"""Temporary probe for validating Chinese PR-Agent output."""

from __future__ import annotations


def normalize_probe_name(name: str) -> str:
    return "-".join(part for part in name.strip().lower().split() if part)
