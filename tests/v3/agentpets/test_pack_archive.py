"""完整素材导入保全图片、映射、校准，覆盖失败可恢复。"""
import base64
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image

from app.plugins.agentpets import AgentPets, ImportPackRequest, require_admin
from app.plugins.agentpets.pack import PackError, PackStore, pack_revision, parse_calibration


@pytest.fixture
def bundle(tmp_path):
    buffer = BytesIO()
    Image.new('RGBA', (200, 100), (255, 0, 0, 255)).save(buffer, format='PNG')
    content = buffer.getvalue()
    image = 'data:image/png;base64,' + base64.b64encode(content).decode()
    raw = {'id': 'pet', 'name': 'Pet', 'grid': {'cols': 2, 'rows': 1}, 'frames': {'idle': 0, 'blink': 1},
           'actions': {'idle': ['idle'], 'blink': ['blink']}, 'action_mappings': {'intent.thinking': 'blink'},
           'calibration': parse_calibration({'left': .1, 'right': .9, 'baseline': .9})}
    data = {}
    store = PackStore(lambda key: deepcopy(data.get(key)), lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    record = store.add(raw, image)
    return store, data, raw, image, content, record


def test_roundtrip_and_copy_preserve_all_material_fields(bundle):
    store, data, _, image, content, old = bundle
    plugin = AgentPets()
    plugin._store = lambda: store
    exported = plugin.api_pack('pet').data
    result = plugin.api_import_pack(ImportPackRequest(pack=exported['pack'], image=exported['sheet_src'], mode='copy'))
    assert result.success and result.data['id'] != old['id']
    copied = store.get(result.data['id'])
    for key in ('name', 'description', 'grid', 'frames', 'actions', 'action_mappings', 'calibration', 'preview', 'avatar'):
        assert copied[key] == old[key]
    assert store.image_path(copied).read_bytes() == content
    assert store.get('pet') == old
    assert len(data['packs']) == 2


def test_replacement_retains_identity_and_previous_image(bundle):
    store, data, raw, image, content, old = bundle
    result = store.import_pack({**raw, 'name': 'Changed'}, image, 'replace', pack_revision(old))
    assert result['id'] == old['id'] and result['created_at'] == old['created_at']
    assert result['name'] == 'Changed' and len(data['packs']) == 1
    assert store.image_path(old).read_bytes() == content
    assert store.image_path(result).read_bytes() == content
    assert data['pack_backup_pet']['record'] == old
    assert result['image_file'] != old['image_file']


@pytest.mark.parametrize('fault', ['stale', 'bad_mapping', 'bad_image', 'backup_failure', 'metadata_failure'])
def test_failed_import_does_not_damage_existing_material(bundle, fault):
    store, data, raw, image, content, old = bundle
    revision = pack_revision(old)
    save = store._save_data
    if fault == 'stale':
        revision = 'old'
    elif fault == 'bad_mapping':
        raw = {**raw, 'action_mappings': {'intent.thinking': 'missing'}}
    elif fault == 'bad_image':
        image = 'data:image/png;base64,broken'
    elif fault == 'backup_failure':
        store._save_data = lambda key, value: False if key.startswith('pack_backup') else save(key, value)
    else:
        store._save_data = lambda key, value: False if key == 'packs' else save(key, value)
    with pytest.raises((PackError, ValueError)):
        store.import_pack({**raw, 'name': 'Changed'}, image, 'replace', revision)
    assert store.get('pet') == old
    assert store.image_path(old).read_bytes() == content


def test_uncertain_commit_keeps_both_images_and_backup(bundle):
    store, data, raw, image, content, old = bundle
    save = store._save_data
    def fail_after_save(key, value):
        save(key, value)
        if key == 'packs':
            raise RuntimeError('write completed but transport failed')
    store._save_data = fail_after_save
    with pytest.raises(RuntimeError):
        store.import_pack({**raw, 'name': 'Changed'}, image, 'replace', pack_revision(old))
    assert store.image_path(old).read_bytes() == content
    assert store.image_path(store.get('pet')).read_bytes() == content
    assert data['pack_backup_pet']['record'] == old


def test_new_collision_and_api_permissions(bundle):
    store, _, raw, image, _, _ = bundle
    with pytest.raises(PackError, match='已存在'):
        store.import_pack(raw, image, 'new')
    plugin = AgentPets()
    route = next(item for item in plugin.get_api() if item['path'] == '/packs/import')
    assert route['auth'] == 'bear' and route['dependencies'][0].dependency is require_admin
