#!/usr/bin/env python3
"""按插件统计单测覆盖率并执行 A 档插件质量门禁。

插件仓包含多代插件和大量历史插件，仓库级覆盖率会把未测试的历史插件计为 0%，不适合
作为协作门禁。这里按插件独立运行 pytest 和 coverage，并只对 ``plugin_quality.json``
声明的插件执行硬阈值，新增插件可先接入 smoke gate，再按维护等级加入覆盖率门禁。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "plugin_quality.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "coverage-reports"


@dataclass(frozen=True)
class CoverageValue:
    """覆盖率统计值，保留命中数、总数和百分比，便于输出和阈值判断复用。"""

    covered: int
    total: int

    @property
    def percent(self) -> float:
        """返回百分比；无可执行项时按 100% 处理，避免纯声明文件误伤。"""
        if self.total == 0:
            return 100.0
        return self.covered / self.total * 100


@dataclass(frozen=True)
class CoverageTarget:
    """单个插件覆盖率门禁配置。"""

    generation: str
    plugin: str
    line: float
    method: float
    changed_line: float

    @property
    def source_path(self) -> Path:
        """插件源码目录。"""
        base = "plugins.v2" if self.generation == "v2" else "plugins"
        return REPO_ROOT / base / self.plugin

    @property
    def test_path(self) -> Path:
        """插件测试目录。"""
        return REPO_ROOT / "tests" / self.generation / self.plugin

    @property
    def report_stem(self) -> str:
        """报告文件名前缀。"""
        return f"{self.generation}-{self.plugin}"


def _read_json(path: Path) -> dict:
    """读取 UTF-8 JSON 文件。"""
    return json.loads(path.read_text(encoding="utf-8"))


def load_targets(config_path: Path = DEFAULT_CONFIG) -> list[CoverageTarget]:
    """读取插件覆盖率门禁配置。"""
    raw_config = _read_json(config_path)
    targets = []
    for item in raw_config.get("coverage", []):
        targets.append(
            CoverageTarget(
                generation=str(item["generation"]),
                plugin=str(item["plugin"]),
                line=float(item["line"]),
                method=float(item["method"]),
                changed_line=float(item["changed_line"]),
            )
        )
    return targets


def calculate_method_coverage(source_file: Path, file_report: dict) -> CoverageValue:
    """统计单文件函数/方法覆盖率。

    只统计 coverage 认为可执行的函数体行；函数声明、纯 docstring 或类型声明不单独计入。
    函数体内至少一条可执行语句被命中，即认为该函数/方法被覆盖。
    """
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    executed = set(file_report.get("executed_lines", []))
    missing = set(file_report.get("missing_lines", []))
    executable = executed | missing
    total = 0
    covered = 0
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for class_node in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        nodes.extend(
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )

    for node in nodes:
        end_line = getattr(node, "end_lineno", node.lineno)
        body_start = min((statement.lineno for statement in node.body), default=node.lineno + 1)
        function_lines = {line for line in executable if body_start <= line <= end_line}
        if not function_lines:
            continue
        total += 1
        if executed & function_lines:
            covered += 1
    return CoverageValue(covered=covered, total=total)


def calculate_changed_line_coverage(changed_lines: dict[str, set[int]], report_files: dict) -> CoverageValue:
    """统计新增/变更行覆盖率，只计算 coverage 识别出的可执行变更行。"""
    covered = 0
    total = 0
    for rel_path, lines in changed_lines.items():
        file_report = report_files.get(rel_path)
        if not file_report:
            continue
        executed = set(file_report.get("executed_lines", []))
        missing = set(file_report.get("missing_lines", []))
        executable = executed | missing
        changed_executable = lines & executable
        total += len(changed_executable)
        covered += len(changed_executable & executed)
    return CoverageValue(covered=covered, total=total)


def collect_changed_lines(base_ref: str, source_prefixes: Iterable[str]) -> dict[str, set[int]]:
    """从 git diff 中提取新增/变更行号，限定在指定插件源码目录内。"""
    prefixes = tuple(prefix.rstrip("/") + "/" for prefix in source_prefixes)
    command = ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", *prefixes]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"无法计算新增行覆盖率：git diff {base_ref}...HEAD 失败。{detail}")
    changed: dict[str, set[int]] = {}
    current_file: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            if not current_file.startswith(prefixes):
                current_file = None
            continue
        if not current_file or not line.startswith("@@"):
            continue
        marker = line.split(" +", 1)[1].split(" ", 1)[0]
        start_text, _, count_text = marker.partition(",")
        start = int(start_text)
        count = int(count_text or "1")
        if count <= 0:
            continue
        changed.setdefault(current_file, set()).update(range(start, start + count))
    return changed


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    """运行子命令并在失败时抛出可读错误。"""
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def build_test_env() -> dict[str, str]:
    """构造插件单测环境，避免继承运行态 CONFIG_DIR 写入真实配置目录。"""
    env = os.environ.copy()
    env.pop("CONFIG_DIR", None)
    env.setdefault("MOVIEPILOT_BACKEND_PATH", str(REPO_ROOT.parent / "MoviePilot"))
    return env


def run_target(target: CoverageTarget, report_dir: Path, base_ref: str | None) -> dict:
    """运行单个插件测试并返回覆盖率摘要。"""
    if not target.source_path.is_dir():
        raise SystemExit(f"插件源码目录不存在：{target.source_path.relative_to(REPO_ROOT)}")
    if not target.test_path.is_dir():
        raise SystemExit(f"插件测试目录不存在：{target.test_path.relative_to(REPO_ROOT)}")

    report_dir.mkdir(parents=True, exist_ok=True)
    json_report = report_dir / f"{target.report_stem}.json"
    env = build_test_env()

    _run([sys.executable, "-m", "coverage", "erase"], env=env)
    _run(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--source",
            str(target.source_path.relative_to(REPO_ROOT)),
            "-m",
            "pytest",
            str(target.test_path.relative_to(REPO_ROOT)),
            "-q",
        ],
        env=env,
    )
    _run([sys.executable, "-m", "coverage", "json", "-o", str(json_report)], env=env)
    report = _read_json(json_report)

    method_total = CoverageValue(covered=0, total=0)
    for rel_path, file_report in report["files"].items():
        source_file = REPO_ROOT / rel_path
        if not source_file.exists():
            continue
        current = calculate_method_coverage(source_file, file_report)
        method_total = CoverageValue(
            covered=method_total.covered + current.covered,
            total=method_total.total + current.total,
        )

    changed = CoverageValue(covered=0, total=0)
    if base_ref:
        changed_lines = collect_changed_lines(base_ref, [str(target.source_path.relative_to(REPO_ROOT))])
        changed = calculate_changed_line_coverage(changed_lines, report["files"])

    totals = report["totals"]
    summary = {
        "generation": target.generation,
        "plugin": target.plugin,
        "line": CoverageValue(covered=totals["covered_lines"], total=totals["num_statements"]),
        "method": method_total,
        "changed_line": changed,
        "json_report": json_report,
    }
    return summary


def _check_threshold(name: str, value: CoverageValue, threshold: float) -> str | None:
    """返回门禁错误文本；通过时返回 None。"""
    if value.percent + 1e-9 < threshold:
        return f"{name} {value.percent:.2f}% ({value.covered}/{value.total}) < {threshold:.2f}%"
    return None


def _print_summary(summary: dict, target: CoverageTarget) -> list[str]:
    """打印单插件覆盖率摘要并返回失败原因。"""
    errors = []
    print(f"{target.generation}/{target.plugin}")
    for name, threshold in (
        ("line", target.line),
        ("method", target.method),
        ("changed_line", target.changed_line),
    ):
        value: CoverageValue = summary[name]
        print(f"  {name}: {value.percent:.2f}% ({value.covered}/{value.total}), threshold={threshold:.2f}%")
        error = _check_threshold(name, value, threshold)
        if error:
            errors.append(error)
    print(f"  report: {summary['json_report']}")
    return errors


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Run per-plugin coverage gates.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="质量门禁配置文件")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="coverage JSON 输出目录")
    parser.add_argument("--base-ref", default=os.environ.get("PLUGIN_COVERAGE_BASE_REF"), help="新增行对比基准")
    parser.add_argument("--plugin", action="append", help="只运行指定插件 ID，可重复传入")
    parser.add_argument("--generation", choices=("v1", "v2"), help="只运行指定代际")
    return parser.parse_args()


def main() -> int:
    """命令入口。"""
    args = parse_args()
    targets = load_targets(args.config)
    if args.plugin:
        selected_plugins = {plugin.lower() for plugin in args.plugin}
        targets = [target for target in targets if target.plugin.lower() in selected_plugins]
    if args.generation:
        targets = [target for target in targets if target.generation == args.generation]
    if not targets:
        print("没有匹配的插件覆盖率门禁目标")
        return 0

    failures = []
    for target in targets:
        summary = run_target(target, args.report_dir, args.base_ref)
        failures.extend(f"{target.generation}/{target.plugin}: {error}" for error in _print_summary(summary, target))

    if failures:
        print("插件覆盖率门禁失败：")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("插件覆盖率门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
