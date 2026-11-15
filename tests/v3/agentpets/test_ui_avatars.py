"""Verify generated UI avatars and the original published image paths."""

import re
from pathlib import Path

import pytest
from PIL import Image

ASSETS = (
    Path(__file__).resolve().parents[3] / "plugins.v3/agentpets/frontend/src/assets"
)
DIST = ASSETS.parents[1] / "dist/assets"
AVATARS = tuple(
    relative.replace("avatar.ui.webp", "avatar.png")
    for relative in re.findall(
        r"@/assets/([^'\"]+avatar\.ui\.webp)",
        (ASSETS.parent / "editor/avatars.ts").read_text(encoding="utf-8"),
    )
)


@pytest.mark.parametrize("relative", AVATARS)
def test_ui_avatar_keeps_all_pixels_and_metadata(relative):
    """A smaller derivative must have the same dimensions, pixels and color metadata."""
    source = ASSETS / relative
    with (
        Image.open(source) as original,
        Image.open(source.with_name("avatar.ui.webp")) as optimized,
    ):
        assert optimized.format == "WEBP"
        assert optimized.size == original.size
        assert optimized.convert("RGBA").tobytes() == original.convert("RGBA").tobytes()
        for key in ("icc_profile", "exif"):
            assert optimized.info.get(key) == original.info.get(key)


def test_ui_avatars_reduce_total_image_bytes():
    """Compression benefits must survive in the committed derivative files."""
    before = sum((ASSETS / relative).stat().st_size for relative in AVATARS)
    after = sum(
        (ASSETS / relative).with_name("avatar.ui.webp").stat().st_size
        for relative in AVATARS
    )
    assert after < before


@pytest.mark.parametrize("relative", AVATARS)
def test_public_png_avatar_path_keeps_original_content(relative):
    """Host declarations and fallback paths continue to receive the original PNG."""
    assert (DIST / relative).read_bytes() == (ASSETS / relative).read_bytes()
    assert not (DIST / relative).with_name("avatar.ui.webp").exists()
