"""完整素材导入保全图片、映射、校准，覆盖失败可恢复。"""
import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.plugins.agentpets import AgentPets, require_admin
from app.plugins.agentpets.packs.constants import MAX_PREVIEW_BYTES, PackError
from app.plugins.agentpets.packs.schema import pack_revision, parse_calibration, parse_pack
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import ImportPackRequest


@pytest.fixture
def bundle(tmp_path):
    """创建带映射和校准的完整素材及图片，用隔离存储模拟导出和恢复"""
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
    """完整导入副本保留元数据与原始图片，不改变源素材"""
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


@pytest.mark.parametrize('field', ['preview', 'avatar'])
def test_thumbnail_capacity_remains_bounded(field):
    """内嵌预览与头像超过字节额度时不能绕过素材校验"""
    image = 'data:image/png;base64,' + base64.b64encode(bytes(MAX_PREVIEW_BYTES + 128)).decode()
    with pytest.raises(PackError, match='128 KiB'):
        parse_pack({'name': 'Too large', 'grid': {'cols': 1, 'rows': 1}, 'frames': {'idle': 0}, field: image})


def test_high_detail_generated_thumbnails_can_be_imported_as_copy(bundle):
    """合法高细节自动缩略图可完整导出再导入，不被旧字符额度误拒绝"""
    store, _, _, _, _, _ = bundle
    content = (Path(__file__).parent / 'fixtures' / 'texture.png').read_bytes()
    image = 'data:image/png;base64,' + base64.b64encode(content).decode()
    original = store.add({'id': 'texture', 'name': 'Texture', 'grid': {'cols': 1, 'rows': 1},
                          'frames': {'idle': 0}}, image)
    # 此合法上传图的自动缩略图超过旧导出额度，必须仍能完整备份和导入副本。
    assert len(base64.b64decode(original['preview'].split(',')[1])) > 49000
    assert len(original['preview']) > 64 * 1024
    plugin = AgentPets()
    plugin._store = lambda: store
    exported = plugin.api_pack('texture').data
    result = plugin.api_import_pack(ImportPackRequest(pack=exported['pack'], image=exported['sheet_src'], mode='copy'))
    assert result.success
    copied = store.get(result.data['id'])
    assert copied['preview'] == original['preview']
    assert copied['avatar'] == original['avatar']
    assert store.image_path(copied).read_bytes() == content


def test_replacement_retains_identity_and_previous_image(bundle):
    """覆盖保留 ID 与创建时间，先备份记录并保留旧图以便恢复"""
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
    """过期修订号、坏素材和备份或元数据写入失败都保全旧素材"""
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
    """提交完成后异常导致状态不明时，两份图片和恢复记录仍可用"""
    store, data, raw, image, content, old = bundle
    save = store._save_data
    def fail_after_save(key, value):
        """先提交内存记录再报错，模拟持久化成功但确认通道失败"""
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
    """新增同 ID 必须失败，完整包导入路由需要管理员权限"""
    store, _, raw, image, _, _ = bundle
    with pytest.raises(PackError, match='已存在'):
        store.import_pack(raw, image, 'new')
    plugin = AgentPets()
    route = next(item for item in plugin.get_api() if item['path'] == '/packs/import')
    assert route['auth'] == 'bear' and route['dependencies'][0].dependency is require_admin
@pytest.mark.parametrize('failure_at', ['write', 'replace'])
def test_failed_image_publish_is_retryable_without_damaging_original(bundle, monkeypatch, failure_at):
    """图片临时写入或原子替换失败后可重试，原始图片保持完好"""
    store, _, raw, image, content, old = bundle
    old_path = store.image_path(old)
    original_write = type(old_path).write_bytes
    def fail_write(path, value):
        """模拟非原图路径只写部分内容后失败，原图读取和写入仍可用"""
        if path != old_path:
            original_write(path, value[:10])
            raise OSError('simulated partial image write')
        return original_write(path, value)
    with monkeypatch.context() as patch:
        if failure_at == 'write':
            patch.setattr(type(old_path), 'write_bytes', fail_write)
        else:
            def fail_replace(*_args):
                """注入发布临时图片的原子替换失败，验证清理与原图保全"""
                raise OSError('simulated image publish failure')
            patch.setattr(type(old_path), 'replace', fail_replace)
        with pytest.raises(OSError):
            store.import_pack({**raw, 'name': 'Changed'}, image, 'replace', pack_revision(old))
    assert store.get('pet') == old
    assert old_path.read_bytes() == content
    assert not list(store._dir.glob('*.tmp'))
    result = store.import_pack({**raw, 'name': 'Changed'}, image, 'replace', pack_revision(old))
    assert result['name'] == 'Changed'
    assert store.image_path(result).read_bytes() == content
