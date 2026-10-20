"""市场专用的有界网络读取，所有请求通过宿主 SDK"""

from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore, Thread, enumerate as enumerate_threads
from time import monotonic
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from .contracts import MarketError

REQUEST_BUDGET = 30
_NETWORK_SLOTS = BoundedSemaphore(4)


def _remaining(deadline: float, market_name: str) -> float:
    """Use one deadline across DNS, headers, redirects and the complete body."""
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise MarketError(f"{market_name} 响应超时，请稍后重试")
    return remaining


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
    """Bound caller latency even when synchronous host DNS cannot be interrupted.

    At most four daemon workers can remain in host I/O across module reloads;
    no work is queued. Excess workers exit before starting host I/O.
    A timed-out worker closes its response when I/O returns and never follows
    another redirect. Safety decisions are always freshly evaluated.
    """
    deadline = monotonic() + REQUEST_BUDGET
    slots = _NETWORK_SLOTS
    if not slots.acquire(blocking=False):
        raise MarketError("市场网络请求繁忙，请稍后重试")
    future: Future[bytes] = Future()

    def run() -> None:
        """Keep ownership of the slot until real I/O has stopped, not just the caller."""
        try:
            # Already registered here: old generations remain visible until I/O exits.
            if sum(worker.name == "agentpets-market" for worker in enumerate_threads()) > 4:
                raise MarketError("市场网络请求繁忙，请稍后重试")
            future.set_result(_read_market_bytes(
                url, limit, market_name=market_name, allowed_hosts=allowed_hosts,
                params=params, redirect_hosts=redirect_hosts,
                redirect_path_prefix=redirect_path_prefix, deadline=deadline,
            ))
        except BaseException as exc:
            future.set_exception(exc)
        finally:
            slots.release()

    try:
        Thread(target=run, name="agentpets-market", daemon=True).start()
    except RuntimeError as exc:
        slots.release()
        raise MarketError("市场网络请求无法启动，请稍后重试") from exc
    try:
        result = future.result(timeout=_remaining(deadline, market_name))
        _remaining(deadline, market_name)
        return result
    except FutureTimeoutError as exc:
        raise MarketError(f"{market_name} 响应超时，请稍后重试") from exc


def _read_market_bytes(
    url: str,
    limit: int,
    *,
    market_name: str,
    allowed_hosts: set[str],
    params: dict[str, Any] | None,
    redirect_hosts: set[str] | None,
    redirect_path_prefix: str | None,
    deadline: float,
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
    current_hosts = allowed_hosts
    try:
        for attempt in range(2):
            _remaining(deadline, market_name)
            validate_resource_url(url, current_hosts)
            if not SecurityUtils.is_safe_url(
                url, current_hosts, strict=True, block_private=True,
                allowed_private_ranges=getattr(settings, "IMAGE_PROXY_ALLOWED_PRIVATE_RANGES", None),
            ):
                raise MarketError(f"{market_name} 地址未通过服务器安全检查，请检查 DNS 与代理网段配置")
            timeout = min(20, _remaining(deadline, market_name))
            with client.get_stream(url, params=params, allow_redirects=False, timeout=timeout) as response:
                _remaining(deadline, market_name)
                if response is None:
                    raise MarketError(f"MoviePilot 服务器无法连接 {market_name}，请检查服务器网络或代理后重试")
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
                    _remaining(deadline, market_name)
                    if len(content) + len(chunk) > limit:
                        raise MarketError(f"{market_name} 响应超过大小限制")
                    content.extend(chunk)
                _remaining(deadline, market_name)
                return bytes(content)
    except MarketError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise MarketError(f"MoviePilot 服务器读取 {market_name} 失败，请检查服务器网络或代理后重试") from exc
    raise MarketError(f"{market_name} 重定向次数超限")
