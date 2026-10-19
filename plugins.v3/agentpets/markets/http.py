"""市场专用的有界网络读取，所有请求通过宿主 SDK"""

from time import monotonic
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from .contracts import MarketError


def validate_resource_url(url: str, allowed_hosts: set[str], *, path_prefix: str | None = None) -> str:
    """校验 HTTPS、精确主机和可选路径前缀，不允许凭据、自定义端口或超长地址

    此处不做 DNS 查询，实际联网前仍须通过宿主的非公网地址检查
    """
    try:
        parsed = urlsplit(url)
        decoded_path = unquote(parsed.path)
        if (len(url) > 2048 or any(character.isspace() for character in url)
                or parsed.scheme != "https" or parsed.netloc not in allowed_hosts
                or parsed.username is not None or parsed.password is not None
            or parsed.fragment or "\\" in url or "\\" in decoded_path
            or any(part in (".", "..") for part in decoded_path.split("/"))
            or (path_prefix is not None and not decoded_path.startswith(path_prefix))):
            raise ValueError("untrusted resource")
    except (TypeError, ValueError) as exc:
        raise MarketError("市场资源地址不受信任") from exc
    return url


def read_market_bytes(
    url: str,
    limit: int,
    *,
    market_name: str,
    allowed_hosts: set[str],
    params: dict[str, Any] | None = None,
    redirect_hosts: set[str] | None = None,
    redirect_path_prefix: str | None = None,
) -> bytes:
    """限时限量读取响应并关闭连接，默认禁止跳转

    仅当显式给出跳转白名单时允许一次 307/308，跳转前重新检查域名、路径和 DNS
    错误消息不包含远程响应正文、请求地址或凭据
    """
    from app.sdk.config import settings
    from app.sdk.network import RequestUtils, SecurityUtils

    client = RequestUtils(proxies=settings.PROXY, timeout=20, verify=True, headers={
        "User-Agent": "MoviePilot-AgentPets/market", "Accept-Encoding": "identity",
        "Accept": "application/json, application/zip",
    })
    deadline = monotonic() + 30
    current_hosts = allowed_hosts
    try:
        for attempt in range(2):
            validate_resource_url(url, current_hosts)
            if not SecurityUtils.is_safe_url(url, current_hosts, strict=True, block_private=True):
                raise MarketError(f"{market_name} 地址未通过安全检查")
            with client.get_stream(url, params=params, allow_redirects=False) as response:
                if response is None:
                    raise MarketError(f"{market_name} 暂时无法连接，请稍后重试")
                if response.status_code in (307, 308) and attempt == 0 and redirect_hosts:
                    target = urljoin(url, response.headers.get("Location", ""))
                    validate_resource_url(target, redirect_hosts, path_prefix=redirect_path_prefix)
                    url, current_hosts, params = target, redirect_hosts, None
                    continue
                if response.status_code == 404:
                    raise MarketError(f"{market_name} 形象不存在或已下架")
                if response.status_code == 429:
                    raise MarketError(f"{market_name} 请求过于频繁，请稍后重试")
                if response.status_code != 200:
                    raise MarketError(f"{market_name} 请求失败，请稍后重试")
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdigit() or int(length) > limit):
                    raise MarketError(f"{market_name} 响应超过大小限制")
                content = bytearray()
                for chunk in response.iter_content(chunk_size=16 * 1024):
                    if monotonic() > deadline:
                        raise MarketError(f"{market_name} 响应超时，请稍后重试")
                    if len(content) + len(chunk) > limit:
                        raise MarketError(f"{market_name} 响应超过大小限制")
                    content.extend(chunk)
                return bytes(content)
    except MarketError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise MarketError(f"{market_name} 网络响应读取失败，请稍后重试") from exc
    raise MarketError(f"{market_name} 重定向次数超限")
