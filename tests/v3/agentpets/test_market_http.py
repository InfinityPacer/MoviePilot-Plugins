"""市场共享请求遵循宿主代理，同时保留无代理行为和安全边界。"""

from contextlib import contextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest

from app.plugins.agentpets.markets.contracts import MarketError
from app.plugins.agentpets.markets.http import read_market_bytes


@pytest.fixture
def network(monkeypatch):
    """替换宿主配置与网络客户端，仅在内存记录代理和安全检查参数。"""
    import app.sdk.config as config
    import app.sdk.network as sdk

    state = {"clients": [], "calls": [], "checks": [], "safe": True, "status": 200, "closed": 0}
    settings = SimpleNamespace(PROXY=None)
    state["settings"] = settings

    class Response:
        """提供可控 HTTP 状态及有限字节，不读取外部网络。"""

        headers = {}

        @property
        def status_code(self):
            """让同一客户端桩覆盖成功与失败的处理分支。"""
            return state["status"]

        def iter_content(self, chunk_size):
            """按生产分块大小提供固定内容。"""
            assert chunk_size == 16 * 1024
            yield b"payload"

    class Client:
        """记录构造参数，检查代理未被忽略或改写。"""

        def __init__(self, **kwargs):
            """保留每次新建客户端的独立参数快照。"""
            state["clients"].append(kwargs)

        @contextmanager
        def get_stream(self, url, **kwargs):
            """记录请求与关闭次数，支持断言失败后没有偷偷改走直连。"""
            state["calls"].append((url, kwargs))
            try:
                yield Response()
            finally:
                state["closed"] += 1

    def check_url(url, allowed_hosts, **kwargs):
        """记录白名单与私网拦截策略，不解析 DNS 或修改宿主服务。"""
        state["checks"].append((url, allowed_hosts, kwargs))
        return state["safe"]

    monkeypatch.setattr(config, "settings", settings)
    monkeypatch.setattr(sdk, "RequestUtils", Client)
    monkeypatch.setattr(sdk.SecurityUtils, "is_safe_url", check_url)
    return state


@pytest.mark.parametrize("url", [
    "https://codex-pets.net/api/pets",
    "https://codex-pets.net/api/pets/example/download",
    "https://openpets.dev/pets/catalog.v3.json",
    "https://zip.openpets.dev/pets/example/example.zip",
    "https://petdex.dev/api/pets/search",
    "https://assets.petdex.dev/pets/example.zip",
])
@pytest.mark.parametrize("proxy", [None, {"http": "http://proxy.test:8080", "https": "http://proxy.test:8080"}])
def test_market_catalogs_and_downloads_follow_mp_proxy(network, url, proxy):
    """三家市场的目录与素材读取都传入当前代理；未配置时保留原有连接方式。"""
    network["settings"].PROXY = proxy
    hosts = {urlsplit(url).hostname}
    assert read_market_bytes(url, 16, market_name="Market", allowed_hosts=hosts) == b"payload"
    options = network["clients"][0]
    assert options["proxies"] is proxy
    assert options["verify"] is True and options["timeout"] == 20
    assert options["headers"]["Accept-Encoding"] == "identity"
    assert network["checks"] == [(url, hosts, {"strict": True, "block_private": True})]
    assert network["calls"] == [(url, {"params": None, "allow_redirects": False})]
    assert network["closed"] == 1


def test_each_request_reads_latest_proxy_without_caching(network):
    """宿主代理变化后新请求采用新值，不缓存旧代理或把地址写死。"""
    proxies = [None, {"https": "http://proxy.test:8080"}, None]
    for proxy in proxies:
        network["settings"].PROXY = proxy
        read_market_bytes("https://codex-pets.net/api/pets", 16,
                          market_name="Market", allowed_hosts={"codex-pets.net"})
    assert [client["proxies"] for client in network["clients"]] == proxies


def test_failed_proxy_request_does_not_retry_direct(network):
    """代理请求失败明确返回失败，不擅自绕过配置再次直连。"""
    network["settings"].PROXY = {"https": "http://proxy.test:8080"}
    network["status"] = 503
    with pytest.raises(MarketError, match="请求失败"):
        read_market_bytes("https://codex-pets.net/api/pets", 16,
                          market_name="Market", allowed_hosts={"codex-pets.net"})
    assert len(network["clients"]) == len(network["calls"]) == network["closed"] == 1
    assert network["clients"][0]["proxies"] == network["settings"].PROXY


def test_proxy_does_not_bypass_private_address_checks(network):
    """即使配置代理，安全检查不通过时仍不得发送请求。"""
    network["settings"].PROXY = {"https": "http://proxy.test:8080"}
    network["safe"] = False
    with pytest.raises(MarketError, match="安全检查"):
        read_market_bytes("https://codex-pets.net/api/pets", 16,
                          market_name="Market", allowed_hosts={"codex-pets.net"})
    assert not network["calls"]
