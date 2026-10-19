"""校准不改变素材内容，旧值冲突与失败不能覆盖现有数据。"""
import base64
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.plugins.agentpets import AgentPets, require_admin
from app.plugins.agentpets.packs.constants import PackError
from app.plugins.agentpets.packs.images import suggest_calibration
from app.plugins.agentpets.packs.schema import parse_calibration
from app.plugins.agentpets.packs.store import PackStore
from app.plugins.agentpets.requests import SaveCalibrationRequest


def fixture_pack(tmp_path):
    """创建含两帧不同透明边界的图片与隔离存储，用于核对参考框和基线"""
    image = Image.new('RGBA', (200, 100))
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 25, 69, 89), fill='white')
    draw.rectangle((120, 10, 179, 79), fill='white')
    stream = BytesIO()
    image.save(stream, format='PNG')
    pack = {'id': 'sample', 'name': 'Sample', 'grid': {'cols': 2, 'rows': 1},
            'frames': {'idle': 0, 'jump': 1}, 'actions': {'idle': ['idle'], 'jump': ['jump']}}
    data = {}
    store = PackStore(lambda key: deepcopy(data.get(key)), lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    record = store.add(pack, 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode())
    return store, data, record, stream.getvalue()


def test_suggestion_uses_union_and_idle_baseline(tmp_path):
    """建议框合并所有帧透明边界，脚底使用 idle 帧而不是最高动作"""
    _, _, pack, content = fixture_pack(tmp_path)
    assert suggest_calibration(content, pack) == parse_calibration({
        'left': .2, 'top': .1, 'right': .8, 'bottom': .9, 'baseline': .9,
    })


def test_save_preserves_original_and_rejects_stale_values(tmp_path):
    """校准只改校准字段，旧值冲突或持久化失败保留原数据和图片"""
    store, data, old, content = fixture_pack(tmp_path)
    calibration = suggest_calibration(content, old)
    new = store.calibrate('sample', calibration, {})
    assert {key: value for key, value in new.items() if key != 'calibration'} == old
    assert store.image_path(new).read_bytes() == content
    snapshot = deepcopy(data)
    with pytest.raises(PackError, match='其他页面'):
        store.calibrate('sample', {}, {})
    assert data == snapshot
    store._save_data = lambda *_: False
    with pytest.raises(PackError, match='保存失败'):
        store.calibrate('sample', {}, calibration)
    assert data == snapshot


def test_eye_coordinates_roundtrip_without_changing_the_sheet(tmp_path):
    """眼位沿用校准保存与冲突保护，不重写精灵图。"""
    store, _, old, content = fixture_pack(tmp_path)
    value = parse_calibration({'eye_x': .4, 'eye_y': .3})
    request = SaveCalibrationRequest(id='sample', calibration=value, expected_calibration={})
    plugin = AgentPets()
    plugin._store = lambda: store
    result = plugin.api_save_calibration(request)
    assert result.success
    assert plugin.api_pack('sample').data['pack']['calibration'] == value
    assert store.image_path(old).read_bytes() == content
    with pytest.raises(PackError, match='其他页面'):
        store.calibrate('sample', {}, {})
    cleared = store.calibrate('sample', {'eye_x': None, 'eye_y': None}, value)
    assert cleared['calibration'] == parse_calibration()


def test_three_landmarks_roundtrip_preserves_legacy_fields_and_original_bytes(tmp_path):
    """三点校准保存回读一致，保留旧眼位字段与原图片字节"""
    store, data, old, content = fixture_pack(tmp_path)
    value = parse_calibration({'eye_x': .5, 'eye_y': .35,
                               'left_eye_x': .3, 'left_eye_y': .32,
                               'right_eye_x': .7, 'right_eye_y': .36,
                               'head_top_x': .48, 'head_top_y': .08})
    plugin = AgentPets()
    plugin._store = lambda: store
    result = plugin.api_save_calibration(SaveCalibrationRequest(id='sample', calibration=value, expected_calibration={}))
    assert result.success
    assert plugin.api_pack('sample').data['pack']['calibration'] == value
    assert store.image_path(old).read_bytes() == content
    snapshot = deepcopy(data)
    with pytest.raises(PackError, match='其他页面'):
        store.calibrate('sample', {}, {})
    assert data == snapshot
    cleared = store.calibrate('sample', {'eye_x': .5, 'eye_y': .35}, value)
    assert cleared['calibration']['left_eye_x'] is None
    assert cleared['calibration']['eye_x'] == .5


@pytest.mark.parametrize('value', [
    {'left_eye_x': .3}, {'head_top_y': .1},
    {'left_eye_x': True, 'left_eye_y': .3},
    {'left_eye_x': .8, 'left_eye_y': .3, 'right_eye_x': .7, 'right_eye_y': .3},
    {'head_top_x': .5, 'head_top_y': .4, 'left_eye_x': .3, 'left_eye_y': .3},
    {'head_top_x': .1, 'head_top_y': .2, 'left': .2},
])
def test_invalid_three_point_calibration(value):
    """拒绝半组坐标、左右颠倒和显示框外的三点校准"""
    with pytest.raises(PackError):
        parse_calibration(value)


def test_legacy_records_are_not_rewritten_on_read(tmp_path):
    """读取旧素材只补运行时默认值，不迁移持久记录"""
    store, data, old, _ = fixture_pack(tmp_path)
    snapshot = deepcopy(data)
    assert store.list() == [old]
    assert parse_calibration({})['head_top_x'] is None
    assert data == snapshot


def test_drag_boundary_rounding_matches_frontend():
    """前后端使用一致的边界舍入容差，不误拒绝合法拖拽结果"""
    value = parse_calibration({'left': .1531, 'right': .9514, 'top': .0423, 'bottom': .9821,
                               'baseline': .9524, 'offset_x': .0291, 'offset_y': -.0153,
                               'head_top_x': .124, 'head_top_y': .0279})
    assert value['head_top_x'] == .124


@pytest.mark.parametrize('value', [
    {'eye_x': .4}, {'eye_y': .3}, {'eye_x': True, 'eye_y': .3},
    {'eye_x': .1, 'eye_y': .3, 'left': .2},
    {'eye_x': .4, 'eye_y': .95, 'baseline': .6},
])
def test_invalid_eye_coordinates(value):
    """半组眼位、非数值和显示框外眼位均拒绝。"""
    with pytest.raises(PackError):
        parse_calibration(value)


@pytest.mark.parametrize('bad', [True, {'top': .9, 'bottom': .91}, {'left': .95},
                               {'baseline': 0}, {'offset_x': .3}, {'right': float('nan')}, {'unknown': 1}])
def test_invalid_calibration(bad):
    """拒绝非法类型、退化参考框、无效基线、非有限偏移和未知字段"""
    with pytest.raises(PackError):
        parse_calibration(bad)


def test_calibration_api_requires_admin_for_save(tmp_path):
    """建议不落盘，保存接口要求管理员并通过读取接口返回已保存校准"""
    store, _, _, _ = fixture_pack(tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    suggestion = plugin.api_suggest_calibration('sample')
    assert suggestion.success
    response = plugin.api_save_calibration(SaveCalibrationRequest(
        id='sample', calibration=suggestion.data, expected_calibration={}))
    assert response.success and response.data.calibration == suggestion.data
    assert plugin.api_pack('sample').data['pack']['calibration'] == suggestion.data
    route = next(item for item in plugin.get_api() if item['path'] == '/packs/calibration' and item['methods'] == ['POST'])
    assert route['dependencies'][0].dependency is require_admin


@pytest.mark.parametrize('rows, extra_index', [(9, 8), (11, 87)])
def test_suggestion_includes_display_completed_codex_frames(rows, extra_index):
    """校准也覆盖显示时补齐的原生动画及视线帧，避免裁掉未显式定义的动作"""
    image = Image.new('RGBA', (800, rows * 100))
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 25, 69, 89), fill='white')
    x, y = extra_index % 8 * 100, extra_index // 8 * 100
    draw.rectangle((x + 10, y + 5, x + 94, y + 94), fill='white')
    stream = BytesIO()
    image.save(stream, format='PNG')
    groups = {'idle': range(6), 'wave': range(24, 28), 'happy-jump': range(32, 37)}
    frames = {'idle': 0}
    actions = {}
    for action, indices in groups.items():
        names = [f'f{index}' for index in indices]
        frames.update(zip(names, indices))
        actions[action] = names
    pack = {'grid': {'cols': 8, 'rows': rows}, 'frames': frames, 'actions': actions}
    assert extra_index not in frames.values()
    assert suggest_calibration(stream.getvalue(), pack) == parse_calibration({
        'left': .1, 'top': .05, 'right': .95, 'bottom': .95, 'baseline': .9,
    })
