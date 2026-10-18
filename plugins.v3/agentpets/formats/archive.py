"""包容器读取契约与安全 ZIP 实现，不解释清单名称、动画或图片格式"""

from __future__ import annotations

import stat
import zipfile
from abc import ABC, abstractmethod
from io import BytesIO
from types import TracebackType
from zlib import error as ZlibError

from ..packs.constants import PackError

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 256
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024


def _normalize_path(value: str, *, parent: str | None = None) -> str:
    """规范容器内相对路径，仅资源引用允许在容器边界内回退父目录"""
    value = value.replace("\\", "/")
    if not value or len(value) > 1024 or "\0" in value or ":" in value or value.startswith("/"):
        raise PackError("包容器仅支持内部相对路径")
    parts = parent.split("/")[:-1] if parent else []
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parent is None or not parts:
                raise PackError("资源路径不能越出包容器")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise PackError("包内资源路径无效")
    return "/".join(parts)


class PackageReader(ABC):
    """提供规范文件名与限额读取的包容器接口，素材解码器只依赖此契约"""

    @property
    @abstractmethod
    def files(self) -> tuple[str, ...]:
        """返回容器内可读文件路径，不包含目录项"""
        raise NotImplementedError

    @abstractmethod
    def read(self, path: str, limit: int) -> bytes:
        """按规范路径有界读取文件，文件缺失、损坏或超限时抛出 PackError"""
        raise NotImplementedError

    def resolve(self, reference: str, *, relative_to: str) -> str:
        """相对已知文件定位资源，允许包内父目录引用但禁止越出边界"""
        parent = _normalize_path(relative_to)
        return _normalize_path(reference, parent=parent)

    @abstractmethod
    def close(self) -> None:
        """释放容器持有的资源，可重复调用"""
        raise NotImplementedError

    def __enter__(self) -> PackageReader:
        """进入容器生命周期，解析失败时同样由退出方法释放资源"""
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None,
                 traceback: TracebackType | None) -> None:
        """退出读取上下文时释放资源，原始异常继续向上传播"""
        self.close()


class ZipPackageReader(PackageReader):
    """安全读取 ZIP 成员，不向磁盘解压，也不假设包内文件命名或内容布局"""

    def __init__(
        self,
        content: bytes,
        *,
        max_bytes: int = MAX_ARCHIVE_BYTES,
        max_entries: int = MAX_ARCHIVE_ENTRIES,
        max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
    ) -> None:
        """先核对压缩大小，再完整验证条目数量、声明总量、路径与文件类型"""
        self._archive: zipfile.ZipFile | None = None
        self._files: dict[str, zipfile.ZipInfo] = {}
        if len(content) > max_bytes:
            raise PackError("ZIP 压缩包超过大小限制")
        try:
            self._archive = zipfile.ZipFile(BytesIO(content))
            entries = self._archive.infolist()
            if len(entries) > max_entries or sum(entry.file_size for entry in entries) > max_uncompressed_bytes:
                raise PackError("ZIP 文件数量或解压总大小超限")
            paths = set()
            for entry in entries:
                path = _normalize_path(entry.filename)
                if path in paths or entry.flag_bits & 1 or stat.S_ISLNK(entry.external_attr >> 16):
                    raise PackError("ZIP 包含重复路径、加密文件或符号链接")
                paths.add(path)
                if not entry.is_dir():
                    self._files[path] = entry
        except PackError:
            self.close()
            raise
        except (OSError, RuntimeError, ValueError, EOFError, zipfile.BadZipFile, ZlibError) as exc:
            self.close()
            raise PackError("ZIP 数据损坏或格式不支持") from exc

    @property
    def files(self) -> tuple[str, ...]:
        """返回已验证文件索引，不暴露 ZIP 的底层条目对象"""
        return tuple(self._files)

    def read(self, path: str, limit: int) -> bytes:
        """先检查单文件声明大小，再限额解压读取，关闭后不能继续读取"""
        if self._archive is None:
            raise PackError("ZIP 容器已关闭")
        path = _normalize_path(path)
        entry = self._files.get(path)
        if entry is None:
            raise PackError("包内资源不存在")
        if limit < 0 or entry.file_size > limit:
            raise PackError("包内资源超过大小限制")
        try:
            with self._archive.open(entry) as source:
                content = source.read(limit + 1)
        except (OSError, RuntimeError, ValueError, EOFError, zipfile.BadZipFile, ZlibError) as exc:
            raise PackError("ZIP 数据损坏或格式不支持") from exc
        if len(content) > limit:
            raise PackError("包内资源超过大小限制")
        return content

    def close(self) -> None:
        """关闭 ZIP 句柄且清除可读资源，重复关闭不产生额外操作"""
        if self._archive is not None:
            self._archive.close()
            self._archive = None
        self._files.clear()
