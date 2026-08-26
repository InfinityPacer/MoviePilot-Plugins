"""在隔离环境中真实安装每份 V3 插件依赖清单。"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
V3_ROOT = REPO_ROOT / "plugins.v3"


def discover_manifests(root: Path = V3_ROOT) -> list[Path]:
    """返回仓库中全部 V3 modern manifest。"""
    return sorted(root.glob("*/pyproject.toml"))


def venv_python(environment: Path, *, windows: bool | None = None) -> Path:
    """返回目标虚拟环境的解释器路径。"""
    is_windows = os.name == "nt" if windows is None else windows
    if is_windows:
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def installation_commands(
    *,
    uv_bin: str,
    python_spec: str,
    environment: Path,
    manifest: Path,
    windows: bool | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """构造与宿主插件安装语义一致的隔离安装和健康检查命令。"""
    python_bin = venv_python(environment, windows=windows)
    return (
        [uv_bin, "venv", "--python", python_spec, str(environment)],
        [
            uv_bin,
            "pip",
            "install",
            "--python",
            str(python_bin),
            "-r",
            str(manifest),
        ],
        [uv_bin, "pip", "check", "--python", str(python_bin)],
    )


def verify_manifest(*, uv_bin: str, python_spec: str, manifest: Path) -> None:
    """在一次性虚拟环境中安装并检查指定清单。"""
    prefix = f"moviepilot-{manifest.parent.name}-"
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        environment = Path(temp_dir) / ".venv"
        for command in installation_commands(
            uv_bin=uv_bin,
            python_spec=python_spec,
            environment=environment,
            manifest=manifest,
        ):
            subprocess.run(command, cwd=REPO_ROOT, check=True)


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Install every V3 plugin manifest in an isolated environment.",
    )
    parser.add_argument("--python", default="3.14", help="目标 Python 解释器")
    parser.add_argument("--uv", default="uv", help="uv 可执行文件")
    return parser.parse_args()


def main() -> int:
    """执行全部 V3 插件依赖的真实安装门禁。"""
    args = parse_args()
    uv_bin = shutil.which(args.uv)
    if not uv_bin:
        print(f"未找到 uv 可执行文件：{args.uv}")
        return 1

    manifests = discover_manifests()
    if not manifests:
        print("未发现 V3 插件 pyproject.toml，拒绝空门禁")
        return 1

    for manifest in manifests:
        relative_manifest = manifest.relative_to(REPO_ROOT)
        print(f"真实安装 {relative_manifest}", flush=True)
        try:
            verify_manifest(
                uv_bin=uv_bin,
                python_spec=args.python,
                manifest=manifest,
            )
        except subprocess.CalledProcessError as err:
            print(f"{relative_manifest} 安装门禁失败，退出码：{err.returncode}")
            return err.returncode or 1

    print(f"V3 插件依赖真实安装门禁通过：{len(manifests)} 份清单")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
