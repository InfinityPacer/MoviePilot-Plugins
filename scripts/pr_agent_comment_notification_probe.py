"""Temporary probe for validating PR-Agent comments and push notifications."""

import subprocess
from dataclasses import dataclass


@dataclass
class ProbeCommand:
    """PR-Agent 测试命令，模拟由外部输入拼接出的执行参数。"""

    endpoint: str
    token: str


def run_probe(command: ProbeCommand) -> str:
    """执行测试命令并返回输出。"""
    shell_command = f"curl -sS {command.endpoint}?token={command.token}"
    return subprocess.check_output(shell_command, shell=True, text=True)
