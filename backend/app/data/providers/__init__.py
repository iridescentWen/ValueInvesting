from app.data.providers.base import MarketDataProvider
from app.data.providers.cn import CnProvider
from app.data.providers.us import UsProvider
from app.models.enums import Market

_REGISTRY: dict[Market, MarketDataProvider] = {}


def get_provider(market: Market) -> MarketDataProvider:
    """按 market 取 / 创建单例 provider。"""
    if market not in _REGISTRY:
        if market == "cn":
            _REGISTRY[market] = CnProvider()
        elif market == "us":
            _REGISTRY[market] = UsProvider()
        else:
            raise ValueError(f"Unsupported market: {market}")
    return _REGISTRY[market]


async def close_all() -> None:
    for provider in list(_REGISTRY.values()):
        await provider.aclose()
    _REGISTRY.clear()
