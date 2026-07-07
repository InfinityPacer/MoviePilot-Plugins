"""Temporary probe for validating PR-Agent describe markers and inline comments."""

import subprocess
from dataclasses import dataclass


@dataclass
class ProbeEvent:
    """PR-Agent 测试事件，模拟由外部输入拼接出的回调命令。"""

    callback_url: str
    payload: str


def send_probe_event(event: ProbeEvent) -> str:
    """发送测试事件并返回命令输出。"""
    command = f"curl -sS {event.callback_url}?payload={event.payload}"
    return subprocess.check_output(command, shell=True, text=True)
