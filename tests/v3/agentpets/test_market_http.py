"""市场共享请求遵循宿主代理，同时保留无代理行为和安全边界。"""

from contextlib import contextmanager
from ipaddress import ip_address
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
    state["real_check"] = sdk.SecurityUtils.is_safe_url

    class Response:
        """提供可控 HTTP 状态及有限字节，不读取外部网络。"""

        def __init__(self):
            """依次取出跳转与最终响应，未指定时沿用通用状态。"""
            self.status, self.headers = state.get("responses", []).pop(0) if state.get("responses") else (
                state["status"], {},
            )

        @property
        def status_code(self):
            """让同一客户端桩覆盖成功与失败的处理分支。"""
            return self.status

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
                if state.get("error"):
                    raise state["error"]
                yield None if state.get("no_response") else Response()
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
    assert network["checks"] == [(url, hosts, {
        "strict": True, "block_private": True, "allowed_private_ranges": None,
    })]
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


def test_each_request_reads_latest_allowed_ranges(network):
    """只复用宿主明确配置的网段；更新和清空后下一请求立即采用新值。"""
    ranges = [["198.18.0.0/15"], [], None]
    for value in ranges:
        network["settings"].IMAGE_PROXY_ALLOWED_PRIVATE_RANGES = value
        read_market_bytes("https://codex-pets.net/api/pets", 16,
                          market_name="Market", allowed_hosts={"codex-pets.net"})
    assert [check[2]["allowed_private_ranges"] for check in network["checks"]] == ranges


@pytest.mark.parametrize(("addresses", "ranges", "allowed"), [
    (["198.18.4.186"], None, False),
    (["198.18.4.186"], [], False),
    (["198.18.4.186"], ["198.18.0.0/15"], True),
    (["198.18.4.186"], ["not-a-network"], False),
    (["127.0.0.1"], ["198.18.0.0/15"], False),
    (["192.168.50.1"], ["198.18.0.0/15"], False),
    (["169.254.169.254"], ["198.18.0.0/15"], False),
    (["::1"], ["198.18.0.0/15"], False),
    (["198.18.4.186", "192.168.50.1"], ["198.18.0.0/15"], False),
    (["198.18.4.186", "2606:4700:4700::1111"], ["198.18.0.0/15"], False),
    (["2606:4700:4700::1111"], ["198.18.0.0/15"], True),
    (["1.1.1.1"], None, True),
    ([], ["198.18.0.0/15"], False),
])
def test_real_host_safety_with_controlled_dns(network, monkeypatch, addresses, ranges, allowed):
    """实验室 DNS 配合真实宿主安全算法，放行 fake-IP 不放行其他私网。"""
    from app.sdk.network import SecurityUtils

    network["settings"].IMAGE_PROXY_ALLOWED_PRIVATE_RANGES = ranges
    monkeypatch.setattr(SecurityUtils, "is_safe_url", network["real_check"])
    monkeypatch.setattr(SecurityUtils, "_hostname_addresses", lambda _host: [ip_address(ip) for ip in addresses])
    if allowed:
        assert read_market_bytes("https://codex-pets.net/api/pets", 16,
                                 market_name="Market", allowed_hosts={"codex-pets.net"}) == b"payload"
    else:
        with pytest.raises(MarketError, match="服务器安全检查"):
            read_market_bytes("https://codex-pets.net/api/pets", 16,
                              market_name="Market", allowed_hosts={"codex-pets.net"})
        assert not network["calls"]


@pytest.mark.parametrize("target", [
    "https://untrusted.test/file.zip", "http://codex-pets.net/file.zip",
    "https://user:password@codex-pets.net/file.zip", "https://codex-pets.net:8443/file.zip",
])
def test_allowed_ranges_do_not_expand_market_hosts(network, target):
    """有网段例外也不接受非内置域名、明文协议、凭据或自定义端口。"""
    network["settings"].IMAGE_PROXY_ALLOWED_PRIVATE_RANGES = ["198.18.0.0/15"]
    with pytest.raises(MarketError, match="不受信任"):
        read_market_bytes(target, 16, market_name="Market", allowed_hosts={"codex-pets.net"})
    assert not network["checks"] and not network["calls"]


@pytest.mark.parametrize("redirect_address", ["198.18.4.187", "192.168.50.1"])
def test_redirect_rechecks_dns_with_configured_ranges(network, monkeypatch, redirect_address):
    """白名单跳转重新验证 DNS；fake-IP 例外不得绕过跳转目标私网检查。"""
    from app.sdk.network import SecurityUtils

    network["settings"].IMAGE_PROXY_ALLOWED_PRIVATE_RANGES = ["198.18.0.0/15"]
    network["responses"] = [(307, {"Location": "https://assets.petdex.dev/pets/test.zip"}), (200, {})]
    monkeypatch.setattr(SecurityUtils, "is_safe_url", network["real_check"])
    monkeypatch.setattr(SecurityUtils, "_hostname_addresses", lambda host: [
        ip_address(redirect_address if host == "assets.petdex.dev" else "198.18.4.186"),
    ])
    kwargs = dict(market_name="Market", allowed_hosts={"petdex.dev"},
                  redirect_hosts={"assets.petdex.dev"}, redirect_path_prefix="/pets/")
    if redirect_address.startswith("198.18."):
        assert read_market_bytes("https://petdex.dev/download", 16, **kwargs) == b"payload"
        assert len(network["calls"]) == network["closed"] == 2
    else:
        with pytest.raises(MarketError, match="服务器安全检查"):
            read_market_bytes("https://petdex.dev/download", 16, **kwargs)
        assert len(network["calls"]) == network["closed"] == 1


@pytest.mark.parametrize("failure", ["no_response", "error"])
def test_connection_failure_identifies_server_without_leaking_details(network, failure):
    """连接失败提示服务器网络，不泄露代理地址、异常正文或引导修改图片安全域。"""
    network[failure] = True if failure == "no_response" else OSError("private-proxy-detail")
    with pytest.raises(MarketError, match="MoviePilot 服务器") as exc:
        read_market_bytes("https://codex-pets.net/api/pets", 16,
                          market_name="Market", allowed_hosts={"codex-pets.net"})
    assert "private-proxy-detail" not in str(exc.value)
    assert "图片安全域" not in str(exc.value)
    assert network["closed"] == 1
