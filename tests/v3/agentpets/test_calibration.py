"""校准不改变素材内容，旧值冲突与失败不能覆盖现有数据。"""
import base64
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.plugins.agentpets import AgentPets, SaveCalibrationRequest, require_admin
from app.plugins.agentpets.pack import PackStore, PackError, parse_calibration, suggest_calibration


def fixture_pack(tmp_path):
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
    _, _, pack, content = fixture_pack(tmp_path)
    assert suggest_calibration(content, pack) == parse_calibration({
        'left': .2, 'top': .1, 'right': .8, 'bottom': .9, 'baseline': .9,
    })


def test_save_preserves_original_and_rejects_stale_values(tmp_path):
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


@pytest.mark.parametrize('bad', [True, {'top': .9, 'bottom': .91}, {'left': .95},
                               {'baseline': 0}, {'offset_x': .3}, {'right': float('nan')}, {'unknown': 1}])
def test_invalid_calibration(bad):
    with pytest.raises(PackError):
        parse_calibration(bad)


def test_calibration_api_requires_admin_for_save(tmp_path):
    store, _, _, _ = fixture_pack(tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    suggestion = plugin.api_suggest_calibration('sample')
    assert suggestion.success
    response = plugin.api_save_calibration(SaveCalibrationRequest(
        id='sample', calibration=suggestion.data, expected_calibration={}))
    assert response.success and response.data['calibration'] == suggestion.data
    assert plugin.api_pack('sample').data['pack']['calibration'] == suggestion.data
    route = next(item for item in plugin.get_api() if item['path'] == '/packs/calibration')
    assert route['dependencies'][0].dependency is require_admin
