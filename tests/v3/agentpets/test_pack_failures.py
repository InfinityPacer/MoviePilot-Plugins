"""素材增删的失败回读不得损坏仍被引用的图片。"""
import base64
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from app.plugins.agentpets import AgentPets
from app.plugins.agentpets.packs.store import PackStore


@pytest.fixture
def fixture(tmp_path):
    """建立内存元数据、临时图片目录和插件门面，模拟素材写入故障"""
    data = {}
    store = PackStore(data.get, lambda key, value: data.__setitem__(key, deepcopy(value)), tmp_path)
    plugin = AgentPets()
    plugin._store = lambda: store
    pack = {"id": "test-pet", "name": "测试", "grid": {"cols": 1, "rows": 1},
            "frames": {"idle": 0}, "actions": {"idle": ["idle"]}}
    buffer = BytesIO()
    Image.new("RGBA", (16, 16), "orange").save(buffer, format="PNG")
    image = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    return plugin, store, data, pack, image


def failure(mode):
    """构造报错、返回失败或静默不写的持久化替身"""
    def save(*_args):
        """按故障模式返回失败或抛异常，始终不改变元数据"""
        if mode == "raise":
            raise RuntimeError("persistence unavailable")
        return False if mode == "false" else None
    return save


@pytest.mark.parametrize("mode", ["raise", "false", "silent"])
def test_failed_delete_preserves_existing_record_and_image(fixture, mode):
    """记录删除未确认时不得回收仍被引用的原始图片"""
    plugin, store, data, pack, image = fixture
    record = store.add(pack, image)
    original = deepcopy(data)
    path = store.image_path(record)
    content = path.read_bytes()
    store._save_data = failure(mode)
    response = plugin.api_delete_pack(SimpleNamespace(id=record["id"]))
    assert response.success is False
    assert data == original
    assert path.read_bytes() == content


@pytest.mark.parametrize("mode", ["raise", "false", "silent"])
def test_failed_add_reports_failure_and_removes_only_its_new_image(fixture, mode, tmp_path):
    """新增持久化失败明确报错，只清理本次未被引用的新图片"""
    plugin, store, data, pack, image = fixture
    store._save_data = failure(mode)
    response = plugin.api_add_pack(SimpleNamespace(pack=pack, image=image))
    assert response.success is False
    assert not data
    assert not list((tmp_path / "packs").glob("*.png"))


def test_ambiguous_commit_keeps_the_image_referenced_by_saved_metadata(fixture):
    """提交后报错时保留已被元数据引用的新图片，避免永久丢失"""
    plugin, store, data, pack, image = fixture

    def save_then_raise(key, value):
        """先完成元数据写入再抛异常，模拟不确定的提交确认"""
        data[key] = deepcopy(value)
        raise RuntimeError("failure after commit")

    store._save_data = save_then_raise
    response = plugin.api_add_pack(SimpleNamespace(pack=pack, image=image))
    assert response.success is False
    record = store.get(pack["id"])
    assert record and store.image_path(record).is_file()


@pytest.mark.parametrize("frame", [{}, [], None, 1])
def test_invalid_frame_reference_returns_a_validation_response(fixture, frame):
    """动作引用非法帧类型时返回格式错误，不落盘任何素材记录"""
    plugin, _, data, pack, image = fixture
    pack["actions"] = {"idle": [frame]}
    response = plugin.api_add_pack(SimpleNamespace(pack=pack, image=image))
    assert response.success is False
    assert "帧" in response.message
    assert not data


def test_add_does_not_remove_an_existing_image_when_reading_it_fails(fixture, tmp_path, monkeypatch):
    """备份旧图读取失败时不得删除或覆盖已存在的可恢复文件"""
    plugin, _, _, pack, image = fixture
    path = tmp_path / "packs" / "test-pet.png"
    path.parent.mkdir()
    path.write_bytes(b"previous recoverable data")
    original = type(path).read_bytes

    def unreadable(item):
        """仅让目标旧图暂时不可读，其他文件仍沿用真实读取行为"""
        if item == path:
            raise PermissionError("temporarily unreadable")
        return original(item)

    monkeypatch.setattr(type(path), "read_bytes", unreadable)
    response = plugin.api_add_pack(SimpleNamespace(pack=pack, image=image))
    assert response.success is False
    assert path.exists()
    assert original(path) == b"previous recoverable data"
