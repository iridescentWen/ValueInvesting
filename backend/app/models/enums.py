from typing import Literal, get_args

Market = Literal["cn", "us", "hk"]

MARKETS: tuple[str, ...] = get_args(Market)
