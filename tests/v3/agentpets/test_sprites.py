"""助手形象插件中素材包形象的声明、素材包校验与存储接口测试。"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

from app.plugins.agentpets import BUILTIN_AVATAR, BUILTIN_PREVIEW, AgentPets, require_admin
from app.plugins.agentpets.pack import (
    BUILTIN_PACK_ID,
    HOST_ACTIONS,
    MAX_PACKS,
    PackError,
    decode_image,
    parse_pack,
    sniff_image,
)

PLUGIN_ROOT = Path(__file__).parents[3] / "plugins.v3" / "agentpets"
DIST = PLUGIN_ROOT / "frontend" / "dist" / "assets"


def _png(width: int = 64, height: int = 32, fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), (255, 128, 0, 255)).save(buffer, format=fmt)
    return buffer.getvalue()


def _data_url(content: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(content).decode("ascii")


def _pack(**overrides) -> dict:
    pack = {
        "id": "pixel-dog",
        "name": "像素狗",
        "grid": {"cols": 2, "rows": 1},
        "frames": {"idle": 0, "talk": 1},
        "actions": {"idle": ["idle"], "speaking": {"frames": ["talk", "idle"], "frame_ms": 200, "loop": True}},
        "random_actions": ["wave"],
    }
    pack.update(overrides)
    return pack


def _sprites(plugin: AgentPets) -> list[dict]:
    """只看素材包形象（renderer），小映的声明由 test_stage 覆盖。"""
    return [pet for pet in plugin.get_agent_pets() if pet["mode"] == "renderer"]


def _decode(data_url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1])))


@pytest.fixture
def plugin(tmp_path: Path) -> AgentPets:
    """插件数据存内存字典、数据目录指向临时目录的测试实例。"""
    instance = AgentPets()
    instance.init_plugin({"enabled": True})
    store: dict = {}
    instance.get_data = lambda key=None: store.get(key)
    instance.save_data = lambda key, value: store.__setitem__(key, value)
    instance.get_data_path = lambda: tmp_path
    return instance


def test_builtin_pack_is_valid_and_shipped() -> None:
    """内置放映猫素材包随联邦产物分发，描述可通过校验。"""
    pack = parse_pack((DIST / "packs" / BUILTIN_PACK_ID / "pack.json").read_text(encoding="utf-8"))

    assert pack["name"] == "放映猫"
    assert pack["grid"] == {"cols": 4, "rows": 2}
    assert list(pack["frames"]) == ["idle", "blink", "talk", "think", "jump", "wave", "sleep", "confused"]
    assert set(pack["random_actions"]) <= set(HOST_ACTIONS)
    assert (DIST / "packs" / BUILTIN_PACK_ID / "sheet.webp").is_file()
    assert (DIST / BUILTIN_PREVIEW).is_file()


def test_declares_builtin_pet_by_default(plugin: AgentPets) -> None:
    """未添加素材包时只声明内置素材包，preview 和 avatar 指向联邦产物内的固定路径。"""
    pets = _sprites(plugin)

    assert len(pets) == 1
    assert pets[0]["key"] == BUILTIN_PACK_ID
    assert pets[0]["component"] == "AgentPetSprite"
    assert pets[0]["api_version"] == 1
    assert pets[0]["preview"] == "packs/projector-cat/preview.png"
    assert pets[0]["avatar"] == BUILTIN_AVATAR
    assert not pets[0]["preview"].startswith("/") and ".." not in pets[0]["preview"]
    assert set(pets[0]["random_actions"]) <= set(HOST_ACTIONS)
    assert "bubbles" not in pets[0]


def test_uploaded_pack_is_declared_with_thumbnail_preview(plugin: AgentPets, tmp_path: Path) -> None:
    """上传的素材包声明为独立形象，预览是裁出的 idle 帧 data URL，图片存入数据目录。"""
    response = plugin.api_add_pack(SimpleNamespace(pack=json.dumps(_pack()), image=_data_url(_png())))

    assert response.success, response.message
    assert (tmp_path / "packs" / "pixel-dog.png").is_file()
    pets = _sprites(plugin)
    assert [pet["key"] for pet in pets] == [BUILTIN_PACK_ID, "pixel-dog"]
    assert pets[1]["component"] == "AgentPetSprite"
    assert pets[1]["preview"].startswith("data:image/png;base64,")
    assert _decode(pets[1]["preview"]).size == (32, 32)
    assert pets[1]["avatar"].startswith("data:image/png;base64,")
    assert pets[1]["random_actions"] == ["wave"]


def test_uploaded_avatar_is_a_square_crop_of_the_idle_character(plugin: AgentPets) -> None:
    """上传方式从 idle 帧不透明区域的顶部裁出方形头像。"""
    sheet = Image.new("RGBA", (128, 64), (0, 0, 0, 0))
    sheet.paste((255, 0, 0, 255), (16, 8, 48, 60))  # idle 格里的角色：宽 32、高 52
    sheet.paste((0, 0, 255, 255), (64, 0, 128, 64))  # 第二格整格填满，不应进入头像
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")

    assert plugin.api_add_pack(SimpleNamespace(pack=_pack(), image=_data_url(buffer.getvalue()))).success
    avatar = _decode(_sprites(plugin)[1]["avatar"]).convert("RGBA")
    assert avatar.size == (32, 32)
    assert avatar.getpixel((0, 0)) == (255, 0, 0, 255)
    assert avatar.getpixel((31, 31)) == (255, 0, 0, 255)


def test_explicit_avatar_in_pack_json_wins(plugin: AgentPets) -> None:
    """JSON 显式填写的头像优先，上传方式也不再自动裁剪。"""
    avatar = "https://example.com/avatar.png"
    assert plugin.api_add_pack(SimpleNamespace(pack=_pack(avatar=avatar), image=_data_url(_png()))).success
    assert _sprites(plugin)[1]["avatar"] == avatar


def test_pack_api_serves_uploaded_sheet_as_data_url(plugin: AgentPets) -> None:
    """形象组件经实例 API 取回素材包和精灵图。"""
    content = _png()
    plugin.api_add_pack(SimpleNamespace(pack=_pack(), image=_data_url(content)))

    data = plugin.api_pack("pixel-dog").data
    assert data["pack"]["frames"] == {"idle": 0, "talk": 1}
    assert data["sheet_src"] == _data_url(content)
    assert plugin.api_pack(BUILTIN_PACK_ID).data["builtin"] is True
    assert plugin.api_pack("missing").success is False


def test_url_pack_requires_http_sheet(plugin: AgentPets) -> None:
    """不上传图片时 sheet 必须是 http(s) 地址，预览可省略。"""
    bad = plugin.api_add_pack(SimpleNamespace(pack=_pack(sheet="sheet.png"), image=None))
    assert bad.success is False and "http" in bad.message

    good = plugin.api_add_pack(SimpleNamespace(pack=_pack(sheet="https://example.com/s.png"), image=None))
    assert good.success is True
    assert plugin.api_pack("pixel-dog").data["sheet_src"] == "https://example.com/s.png"
    declared = _sprites(plugin)[1]
    assert "preview" not in declared and "avatar" not in declared


def test_url_pack_declares_avatar_only_when_given(plugin: AgentPets) -> None:
    """URL 方式不下载远程图，头像只在 JSON 显式填写时声明。"""
    pack = _pack(sheet="https://example.com/s.png", avatar="data:image/png;base64,AAAA")
    assert plugin.api_add_pack(SimpleNamespace(pack=pack, image=None)).success
    assert _sprites(plugin)[1]["avatar"] == "data:image/png;base64,AAAA"


def test_delete_removes_record_and_image(plugin: AgentPets, tmp_path: Path) -> None:
    """删除素材包同时删除图片；内置素材包不可删除。"""
    plugin.api_add_pack(SimpleNamespace(pack=_pack(), image=_data_url(_png())))

    assert plugin.api_delete_pack(SimpleNamespace(id="pixel-dog")).success is True
    assert not (tmp_path / "packs" / "pixel-dog.png").exists()
    assert [pet["key"] for pet in _sprites(plugin)] == [BUILTIN_PACK_ID]
    assert plugin.api_delete_pack(SimpleNamespace(id=BUILTIN_PACK_ID)).success is False
    assert plugin.api_delete_pack(SimpleNamespace(id="pixel-dog")).success is False


def test_store_rejects_duplicates_reserved_ids_and_overflow(plugin: AgentPets) -> None:
    """ID 不能重复、不能占用内置 ID，数量有上限。"""
    url = "https://example.com/s.png"
    assert plugin.api_add_pack(SimpleNamespace(pack=_pack(sheet=url), image=None)).success
    duplicate = plugin.api_add_pack(SimpleNamespace(pack=_pack(sheet=url), image=None))
    assert duplicate.success is False and "已存在" in duplicate.message
    reserved = plugin.api_add_pack(SimpleNamespace(pack=_pack(id=BUILTIN_PACK_ID, sheet=url), image=None))
    assert reserved.success is False
    stage_key = plugin.api_add_pack(SimpleNamespace(pack=_pack(id="ying", sheet=url), image=None))
    assert stage_key.success is False and "内置形象" in stage_key.message
    for index in range(1, MAX_PACKS):
        plugin.api_add_pack(SimpleNamespace(pack=_pack(id=f"p{index}", sheet=url), image=None))
    overflow = plugin.api_add_pack(SimpleNamespace(pack=_pack(id="last", sheet=url), image=None))
    assert overflow.success is False and str(MAX_PACKS) in overflow.message


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": ""}, "name"),
        ({"id": "Bad ID"}, "id"),
        ({"grid": {"cols": 0, "rows": 1}}, "grid.cols"),
        ({"frames": {"talk": 0}}, "idle"),
        ({"frames": {"idle": 2}}, "frames.idle"),
        ({"actions": {"x": ["nope"]}}, "未定义的帧"),
        ({"actions": {"x": {"frames": ["idle"], "frame_ms": 1}}}, "frame_ms"),
        ({"actions": {"x": {"frames": ["idle"], "loop": "yes"}}}, "loop"),
        ({"random_actions": ["dance"]}, "宿主动作名"),
        ({"preview": "javascript:alert(1)"}, "preview"),
        ({"avatar": "file:///etc/passwd"}, "avatar"),
    ],
)
def test_parse_pack_rejects_invalid_structure(overrides: dict, message: str) -> None:
    """素材包结构错误给出可读的中文原因。"""
    with pytest.raises(PackError, match=message):
        parse_pack(_pack(**overrides))


def test_parse_pack_rejects_bad_json_and_oversize() -> None:
    with pytest.raises(PackError, match="解析失败"):
        parse_pack("{")
    with pytest.raises(PackError, match="64KB"):
        parse_pack(" " * (64 * 1024 + 1))
    with pytest.raises(PackError, match="顶层"):
        parse_pack("[]")


def test_image_validation_checks_type_size_and_grid(plugin: AgentPets) -> None:
    """按文件头识别类型，拒绝非图片、超限和与网格不匹配的精灵图。"""
    assert sniff_image(_png(fmt="WEBP"))[0] == "image/webp"
    with pytest.raises(PackError, match="PNG"):
        sniff_image(b"<svg></svg>")
    with pytest.raises(PackError, match="4MB"):
        sniff_image(b"\x89PNG\r\n\x1a\n" + b"0" * (4 * 1024 * 1024))
    with pytest.raises(PackError, match="data URL"):
        decode_image("https://example.com/a.png")
    with pytest.raises(PackError, match="base64"):
        decode_image("data:image/png;base64,***")

    uneven = plugin.api_add_pack(SimpleNamespace(pack=_pack(), image=_data_url(_png(width=65))))
    assert uneven.success is False and "整除" in uneven.message
    fake = plugin.api_add_pack(SimpleNamespace(pack=_pack(), image=_data_url(b"\x89PNG\r\n\x1a\nbroken")))
    assert fake.success is False and "无法解码" in fake.message


def test_write_endpoints_require_admin(plugin: AgentPets) -> None:
    """读取接口只要求登录，添加和删除额外要求管理员。"""
    routes = {(route["path"], route["methods"][0]): route for route in plugin.get_api()}

    assert all(route["auth"] == "bear" for route in routes.values())
    assert "dependencies" not in routes[("/packs", "GET")]
    assert "dependencies" not in routes[("/pack", "GET")]
    for key in (("/packs", "POST"), ("/packs/delete", "POST")):
        assert [dep.dependency for dep in routes[key]["dependencies"]] == [require_admin]

    assert require_admin(SimpleNamespace(super_user=True)).super_user is True
    with pytest.raises(HTTPException) as error:
        require_admin(SimpleNamespace(super_user=False))
    assert error.value.status_code == 403


def test_packs_api_lists_builtin_first(plugin: AgentPets) -> None:
    plugin.api_add_pack(SimpleNamespace(pack=_pack(sheet="https://example.com/s.png"), image=None))

    packs = plugin.api_packs().data
    assert [(pack["id"], pack["builtin"], pack["source"]) for pack in packs] == [
        (BUILTIN_PACK_ID, True, "builtin"),
        ("pixel-dog", False, "url"),
    ]
    assert packs[1]["frame_count"] == 2 and packs[1]["action_count"] == 2
