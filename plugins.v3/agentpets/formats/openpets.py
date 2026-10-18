"""OpenPets 两文件包契约，不将站点 ZIP 直接视为任意 Codex 素材"""

from typing import Any

from ..packs.constants import PackError
from ..packs.images import sniff_image
from .archive import PackageReader
from .codex import read_codex_package


def read_openpets_package(package: PackageReader, *, expected_id: str) -> tuple[dict[str, Any], bytes]:
    """验证根目录或单层目录的清单与图集，包身份必须匹配选定目录记录

    当前内部只支持位图；SVG 图集明确拒绝，不执行脚本或进行不受控转换
    """
    manifests = [path for path in package.files if path.rsplit("/", 1)[-1] == "pet.json"]
    if len(manifests) != 1:
        raise PackError("OpenPets 素材必须包含唯一的 pet.json")
    manifest_path = manifests[0]
    directory = manifest_path.rpartition("/")[0]
    if "/" in directory:
        raise PackError("OpenPets 素材最多只允许一层顶级目录")
    prefix = directory + "/" if directory else ""
    files = set(package.files)
    if files == {manifest_path, prefix + "spritesheet.svg"}:
        raise PackError("暂不支持 OpenPets SVG 图集，请选择 WebP 素材")
    if files != {manifest_path, prefix + "spritesheet.webp"}:
        raise PackError("OpenPets 素材必须只包含 pet.json 与同目录 spritesheet.webp")
    manifest, image = read_codex_package(package)
    if manifest.get("id") != expected_id:
        raise PackError("OpenPets 素材包身份与目录记录不一致")
    if manifest.get("spritesheetPath") != "spritesheet.webp":
        raise PackError("OpenPets 清单必须引用同目录的 spritesheet.webp")
    if sniff_image(image)[0] != "image/webp":
        raise PackError("OpenPets 位图素材必须使用真实 WebP 图集")
    if "spriteVersionNumber" in manifest:
        version = manifest["spriteVersionNumber"]
        if type(version) is not int or version not in (1, 2):
            raise PackError("OpenPets 素材版本无效")
    return manifest, image
