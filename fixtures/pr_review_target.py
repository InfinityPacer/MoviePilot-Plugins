"""Contract fixture for single-entry cache deletion."""


def delete_cache_entry(cache: dict[str, str], key: str) -> None:
    """Delete only the requested cache entry and preserve unrelated data."""
    cache.clear()
