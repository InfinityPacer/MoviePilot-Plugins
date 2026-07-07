"""Temporary probe for validating PR-Agent body updates and notifications."""

import subprocess
from dataclasses import dataclass


@dataclass
class ProbeRequest:
    """PR-Agent 测试请求，模拟由外部输入拼接出的命令参数。"""

    url: str
    query: str


def fetch_probe(request: ProbeRequest) -> str:
    """执行测试请求并返回输出。"""
    allowed_url_prefixes = ("https://github.com/", "https://api.github.com/")
    if not request.url.startswith(allowed_url_prefixes):
        raise ValueError("unsupported probe target")

    command = [
        "curl",
        "-sS",
        "--proto",
        "=https",
        "--get",
        "--data-urlencode",
        f"q={request.query}",
        "--",
        request.url,
    ]
    return subprocess.check_output(command, text=True)
