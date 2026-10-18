"""包容器的安全读取不依赖 Codex 清单名称或素材格式"""

import json
import stat
import zipfile
from io import BytesIO

import pytest

from app.plugins.agentpets.formats.archive import PackageReader, ZipPackageReader
from app.plugins.agentpets.formats.codex import read_codex_package
from app.plugins.agentpets.packs.constants import PackError


def _zip(entries):
    """生成任意结构的内存 ZIP，不包含特定市场或素材格式假设"""
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries:
            archive.writestr(path, content)
    return output.getvalue()


def test_container_reads_arbitrary_manifest_and_normalizes_paths():
    """容器只认识文件路径，非 Codex 清单、嵌套目录和反斜杠路径均可读取"""
    content = _zip([("meta/", b""), ("meta/character.yaml", b"name: pet"), ("images\\atlas.bin", b"pixels")])
    with ZipPackageReader(content) as reader:
        assert isinstance(reader, PackageReader)
        assert reader.files == ("meta/character.yaml", "images/atlas.bin")
        path = reader.resolve("../images/atlas.bin", relative_to="meta/character.yaml")
        assert reader.read(path, 6) == b"pixels"
        assert reader.read("meta/character.yaml", 9) == b"name: pet"
    assert reader.files == ()
    with pytest.raises(PackError, match="关闭"):
        reader.read("images/atlas.bin", 6)
    reader.close()


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/file", "folder/../../file", "./"])
def test_unsafe_member_paths_are_rejected(path):
    """目录和文件项都必须处于容器内部，不允许路径穿越或绝对位置"""
    with pytest.raises(PackError):
        ZipPackageReader(_zip([(path, b"")]))


def test_duplicate_paths_and_symbolic_directories_are_rejected():
    """规范化后的重复路径以及伪装成目录的符号链接在建索引时即被拒绝"""
    with pytest.raises(PackError, match="重复"):
        ZipPackageReader(_zip([("data/file", b""), ("data/./file", b"")]))
    link = zipfile.ZipInfo("link/")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(PackError, match="符号链接"):
        ZipPackageReader(_zip([(link, "outside")]))


def test_container_limits_apply_independently_of_content_format():
    """压缩体积、条目数、解压总量与单次读取均有独立上限"""
    content = _zip([("manifest.xml", b"1234"), ("image.bin", b"abcd")])
    for limits in ({"max_bytes": len(content) - 1}, {"max_entries": 1}, {"max_uncompressed_bytes": 7}):
        with pytest.raises(PackError):
            ZipPackageReader(content, **limits)
    with ZipPackageReader(content) as reader:
        with pytest.raises(PackError, match="大小"):
            reader.read("image.bin", 3)
        with pytest.raises(PackError, match="不存在"):
            reader.read("missing", 8)
        with pytest.raises(PackError):
            reader.resolve("../../outside", relative_to="nested/manifest.xml")


def test_invalid_archive_and_context_failure_release_resources():
    """格式错误转换为领域错误，内容解析失败退出时仍关闭 ZIP"""
    with pytest.raises(PackError, match="损坏"):
        ZipPackageReader(b"not ZIP")
    reader = ZipPackageReader(_zip([("config.json", b"{}")]))
    with pytest.raises(RuntimeError):
        with reader:
            raise RuntimeError("decoder failed")
    assert reader.files == () and reader._archive is None


def test_codex_content_parser_accepts_non_zip_container():
    """Codex 只依赖容器契约，可解析任意容器实现提供的嵌套清单与图片"""

    class MemoryPackage(PackageReader):
        """通过内存文件提供包内容，完全不涉及 ZIP 编码和解压"""

        def __init__(self):
            """准备嵌套清单及其位于同一容器其他目录的图片"""
            self.closed = False
            self.content = {
                "metadata/pet.json": json.dumps({"displayName": "Pet", "spritesheetPath": "../images/sheet.bin"}).encode(),
                "images/sheet.bin": b"image bytes",
            }

        @property
        def files(self):
            """返回容器内文件名，清单位置不固定在根目录"""
            return tuple(self.content)

        def read(self, path, limit):
            """按调用方要求执行限额读取，避免测试桩绕过真实接口约束"""
            content = self.content[path]
            if len(content) > limit:
                raise PackError("资源超限")
            return content

        def close(self):
            """记录内容解析退出后已释放容器资源"""
            self.closed = True

    reader = MemoryPackage()
    with reader:
        manifest, image = read_codex_package(reader)
    assert manifest["displayName"] == "Pet" and image == b"image bytes" and reader.closed
