"""Thumbnail generation shares decoding without changing pixels or overrides."""

from io import BytesIO

import pytest
from PIL import Image

from app.plugins.agentpets.packs import images


@pytest.mark.parametrize("preview,avatar", [(False, False), (True, False), (False, True), (True, True)])
def test_shared_idle_frame_preserves_images_and_overrides(monkeypatch, preview, avatar):
    """Both outputs match the old independent functions, with at most one crop."""
    output = BytesIO()
    source = Image.new("RGBA", (240, 360))
    source.paste((200, 100, 30, 255), (40, 40, 200, 330))
    source.save(output, format="PNG")
    content = output.getvalue()
    pack = {"grid": {"cols": 1, "rows": 1}, "frames": {"idle": 0},
            "preview": "https://example.com/preview.png" if preview else "",
            "avatar": "https://example.com/avatar.png" if avatar else ""}
    expected = (pack["preview"] or images.first_frame_preview(content, pack),
                pack["avatar"] or images.first_frame_avatar(content, pack))
    original = images._idle_frame
    calls = []

    def crop(*args):
        """Count full-sheet decodes, not cheap thumbnail resizes."""
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(images, "_idle_frame", crop)
    assert images.first_frame_images(content, pack) == expected
    assert len(calls) == (0 if preview and avatar else 1)
