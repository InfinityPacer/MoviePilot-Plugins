"""Content paths separate rebuilt federation graphs without changing business versions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.frontend_assets import frontend_asset_directory

ROOT = Path(__file__).parents[3] / "plugins.v3/agentpets"
IDENTITY = "a" * 64


def _manifest(root: Path, **updates) -> Path:
    """Create an isolated complete entry and its manifest for resolver boundary tests."""
    target = root / "frontend/dist/asset-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    directory = f"assets/build-{IDENTITY}"
    entry = target.parent / directory / "remoteEntry.js"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("export const get = () => {};", encoding="utf-8")
    data = {"schema_version": 1, "build_id": IDENTITY, "asset_directory": directory}
    data.update(updates)
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def test_current_render_mode_uses_the_published_content_identity() -> None:
    """Config, Page and all three Pet components resolve through the same manifest path."""
    manifest = json.loads((ROOT / "frontend/dist/asset-manifest.json").read_text(encoding="utf-8"))
    mode, directory = AgentPets.get_render_mode()
    assert mode == "vue"
    assert directory == "frontend/dist/" + manifest["asset_directory"]
    entry = (ROOT / directory / "remoteEntry.js").read_text(encoding="utf-8")
    for name in ("AgentPet", "AgentPetSprite", "AgentPetCodex", "Config", "Page"):
        assert f'"./{name}"' in entry


def test_legacy_layout_without_manifest_remains_supported(tmp_path: Path) -> None:
    """Older source packages can still register their original static directory."""
    assert frontend_asset_directory(tmp_path) == "frontend/dist/assets"


@pytest.mark.parametrize("updates", [
    {"schema_version": 2}, {"schema_version": True}, {"build_id": "../other"}, {"build_id": "a" * 63},
    {"build_id": "A" * 64}, {"asset_directory": "assets/../other"},
    {"asset_directory": "assets/build-" + "b" * 64},
])
def test_invalid_manifest_never_falls_back_to_a_stale_entry(tmp_path: Path, updates) -> None:
    """Malformed content identity is explicit failure rather than old-cache reuse."""
    _manifest(tmp_path, **updates)
    with pytest.raises(ValueError):
        frontend_asset_directory(tmp_path)


@pytest.mark.parametrize("body", ["null", "[]", "broken json"])
def test_invalid_json_manifest_is_rejected(tmp_path: Path, body: str) -> None:
    """Non-object or malformed manifests cannot select runtime resources."""
    manifest = _manifest(tmp_path)
    manifest.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        frontend_asset_directory(tmp_path)


def test_missing_content_entry_does_not_register_legacy_assets(tmp_path: Path) -> None:
    """Publishing the manifest without its entry must fail until the graph is complete."""
    _manifest(tmp_path)
    (tmp_path / f"frontend/dist/assets/build-{IDENTITY}/remoteEntry.js").unlink()
    with pytest.raises(ValueError):
        frontend_asset_directory(tmp_path)


def test_manifest_identity_is_reread_after_a_new_build(tmp_path: Path) -> None:
    """A replaced manifest changes the URL even without a Python process restart."""
    manifest = _manifest(tmp_path)
    assert frontend_asset_directory(tmp_path).endswith(IDENTITY)
    changed = "b" * 64
    entry = manifest.parent / f"assets/build-{changed}/remoteEntry.js"
    entry.parent.mkdir()
    entry.write_text("new build", encoding="utf-8")
    manifest.write_text(json.dumps({"schema_version": 1, "build_id": changed,
                                    "asset_directory": f"assets/build-{changed}"}), encoding="utf-8")
    assert frontend_asset_directory(tmp_path).endswith(changed)


def test_host_projects_one_content_entry_for_all_pet_components() -> None:
    """The owning host projector must publish the same URL for pages and every pet kind."""
    from app.runtime.extensions.plugin.projection import PluginProjection

    plugin = AgentPets()
    plugin.init_plugin({"enabled": True})
    plugin.get_data = lambda key=None: None
    projection = PluginProjection(
        {"AgentPets": plugin},
        remote_entry_factory=lambda plugin_id, directory: f"/plugin/file/{plugin_id.lower()}/{directory}/remoteEntry.js",
    )
    remotes = projection.remotes()
    pets = projection.agent_pets()
    assert len(remotes) == 1 and pets
    assert {pet["component"] for pet in pets} == {"AgentPet", "AgentPetSprite", "AgentPetCodex"}
    assert {pet["remote_url"] for pet in pets} == {remotes[0]["url"]}
    assert f"/build-{json.loads((ROOT / 'frontend/dist/asset-manifest.json').read_text(encoding='utf-8'))['build_id']}/" in remotes[0]["url"]
    assert remotes[0]["url"].endswith("/remoteEntry.js?v=" + plugin.plugin_version)
