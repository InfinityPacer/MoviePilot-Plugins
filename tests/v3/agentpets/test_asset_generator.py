"""Offline checks for the generated asset JSON boundary."""

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[3] / "scripts" / "agentpets" / "convert_agentmascot.py"


def test_json_writer_uses_formatter_and_utf8_lf(tmp_path, monkeypatch):
    """验证生成 JSON 经过既有格式化器且按 UTF-8/LF 原样落盘"""
    converter = runpy.run_path(str(SCRIPT))
    value = {"name": "\u5c0f\u5929\u7167", "frames": [1, 2, 3]}
    formatted = json.dumps(value, ensure_ascii=False) + "\n"

    def run(command, **kwargs):
        """检查格式化器调用参数并返回预期的 UTF-8 文本"""
        assert command == ["node", "prettier.cjs", "--parser", "json"]
        assert json.loads(kwargs["input"]) == value
        assert kwargs["check"] is True
        assert kwargs["encoding"] == "utf-8"
        assert "shell" not in kwargs
        return SimpleNamespace(stdout=formatted)

    monkeypatch.setattr(converter["subprocess"], "run", run)
    target = tmp_path / "pack.json"
    converter["write_json"](target, value, ["node", "prettier.cjs", "--parser", "json"])
    assert target.read_bytes() == formatted.encode("utf-8")
    assert b"\r" not in target.read_bytes()


def test_formatter_failure_preserves_existing_json(tmp_path, monkeypatch):
    """格式化失败时保留原 JSON，避免先覆盖再报错"""
    converter = runpy.run_path(str(SCRIPT))
    target = tmp_path / "pack.json"
    target.write_bytes(b"original\n")

    def fail(*_args, **_kwargs):
        """模拟格式化子进程失败，不触发真实工具执行"""
        raise subprocess.CalledProcessError(1, ["node", "prettier.cjs"])

    monkeypatch.setattr(converter["subprocess"], "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        converter["write_json"](target, {}, ["node", "prettier.cjs"])
    assert target.read_bytes() == b"original\n"


def test_missing_node_fails_before_creating_assets(tmp_path, monkeypatch):
    """缺少 Node 时在创建素材目录之前失败"""
    converter = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr(converter["shutil"], "which", lambda _name: None)
    target = tmp_path / "assets"
    with pytest.raises(RuntimeError, match="Node.js"):
        converter["convert"](tmp_path / "input.json", target, "unused")
    assert not target.exists()
