"""Resolve one content-addressed entry for every AgentPets federated component."""
from __future__ import annotations

import json
import re
from pathlib import Path

LEGACY_ASSETS = "frontend/dist/assets"


def frontend_asset_directory(plugin_dir: Path) -> str:
    """Read the build identity; invalid new manifests never silently select old assets."""
    manifest = plugin_dir / "frontend/dist/asset-manifest.json"
    if manifest.is_symlink():
        raise ValueError("Invalid AgentPets asset manifest link")
    if not manifest.exists():
        return LEGACY_ASSETS
    if not manifest.is_file() or manifest.stat().st_size > 65536:
        raise ValueError("Invalid AgentPets asset manifest")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    schema = data.get("schema_version") if isinstance(data, dict) else None
    if not isinstance(schema, int) or isinstance(schema, bool) or schema != 1:
        raise ValueError("Unsupported AgentPets asset manifest")
    build_id = data.get("build_id")
    if not isinstance(build_id, str) or not re.fullmatch(r"[0-9a-f]{64}", build_id):
        raise ValueError("Invalid AgentPets build identity")
    directory = f"assets/build-{build_id}"
    if data.get("asset_directory") != directory:
        raise ValueError("Invalid AgentPets asset directory")
    relative = f"frontend/dist/{directory}"
    entry = plugin_dir / relative / "remoteEntry.js"
    if (entry.is_symlink() or entry.parent.is_symlink() or not entry.is_file()
            or not entry.resolve().is_relative_to(plugin_dir.resolve())):
        raise ValueError("Missing or invalid AgentPets content entry")
    return relative
