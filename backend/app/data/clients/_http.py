import httpx

DEFAULT_TIMEOUT = 15.0
DEFAULT_UA = "valueinvesting-backend/0.1"


def make_client(
    *,
    base_url: str = "",
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """统一的 httpx.AsyncClient 工厂。

    测试时传 `transport=httpx.MockTransport(handler)` 可在不打真实网络的
    前提下拦截所有请求。
    """
    merged: dict[str, str] = {"User-Agent": DEFAULT_UA}
    if headers:
        merged.update(headers)
    return httpx.AsyncClient(
        base_url=base_url,
        headers=merged,
        timeout=timeout,
        transport=transport,
    )
