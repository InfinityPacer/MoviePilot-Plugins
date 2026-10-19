"""Keep the user-provided Z256 Kurisu independent from existing imported Pets."""

import hashlib
import json
from pathlib import Path

from app.plugins.agentpets.packs.constants import BUILTIN_PACK_IDS, RESERVED_IDS
from app.plugins.agentpets.packs.schema import codex_pet_version
from app.plugins.agentpets.packs.store import load_builtin_pack
from PIL import Image

ASSETS = Path(__file__).parents[3] / 'plugins.v3' / 'agentpets' / 'frontend' / 'src' / 'assets'
KEY = 'builtin-kurisu-z256'


def test_original_png_and_saved_calibration_are_packaged_without_a_new_identity_collision():
    """The built-in uses a new reserved key while preserving the original PNG bytes."""
    folder = ASSETS / 'packs' / KEY
    pack = load_builtin_pack(ASSETS, KEY)
    provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    assert KEY in BUILTIN_PACK_IDS and KEY in RESERVED_IDS
    assert 'kurisu-v2' not in RESERVED_IDS
    assert pack['id'] == KEY and pack['description'] == 'z256专属'
    assert codex_pet_version(pack) == 'v2'
    assert pack['calibration'] == provenance['calibration']
    assert set(pack['actions']) == set(provenance['original_actions']) | set(provenance['derived_actions'])
    digest = hashlib.sha256((folder / 'sheet.png').read_bytes()).hexdigest()
    assert digest == provenance['image_sha256']
    assert digest == 'b09ee371efb0b51cdb5a88346389f01d29251c692a5448fe463b1b258ba67af7'
    for name, expected in [('sheet.png', (1536, 2288)), ('avatar.png', None), ('preview.png', None)]:
        with Image.open(folder / name) as image:
            assert image.format == 'PNG'
            assert image.width > 0 and image.height > 0
            if expected:
                assert image.size == expected


def test_webp_render_retains_every_original_rgba_pixel():
    """Keep the original PNG while using the existing WebP static delivery path."""
    folder = ASSETS / 'packs' / KEY
    pack = load_builtin_pack(ASSETS, KEY)
    provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    assert pack['sheet'] == provenance['render_image'] == 'sheet.webp'
    assert hashlib.sha256((folder / 'sheet.webp').read_bytes()).hexdigest() == provenance['render_image_sha256']
    with Image.open(folder / 'sheet.png') as original, Image.open(folder / 'sheet.webp') as rendered:
        assert rendered.format == 'WEBP'
        assert rendered.size == original.size
        assert rendered.convert('RGBA').tobytes() == original.convert('RGBA').tobytes()
