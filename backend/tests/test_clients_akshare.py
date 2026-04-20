"""AkShare 客户端测试：用 monkeypatch 把 `ak.*` 替换成返回固定 DataFrame 的 stub。"""

import pandas as pd
import pytest

import app.data.clients.akshare as ak_mod
from app.data.clients.akshare import AkshareClient


@pytest.mark.asyncio
async def test_list_a_stocks_calls_underlying_and_returns_df(monkeypatch) -> None:
    df = pd.DataFrame({"code": ["600519", "000001"], "name": ["贵州茅台", "平安银行"]})
    calls: list[str] = []

    def _stub():
        calls.append("stock_info_a_code_name")
        return df

    monkeypatch.setattr(ak_mod.ak, "stock_info_a_code_name", _stub)

    client = AkshareClient(concurrency=2)
    result = await client.list_a_stocks()

    assert calls == ["stock_info_a_code_name"]
    assert list(result["code"]) == ["600519", "000001"]


@pytest.mark.asyncio
async def test_get_daily_bars_forwards_kwargs(monkeypatch) -> None:
    captured: dict = {}

    def _stub(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            {
                "日期": ["2024-01-02"],
                "开盘": [10.0],
                "最高": [11.0],
                "最低": [9.5],
                "收盘": [10.5],
                "成交量": [100000],
            }
        )

    monkeypatch.setattr(ak_mod.ak, "stock_zh_a_hist", _stub)

    client = AkshareClient()
    df = await client.get_daily_bars("600519", "20240101", "20240131")

    assert captured == {
        "symbol": "600519",
        "period": "daily",
        "start_date": "20240101",
        "end_date": "20240131",
        "adjust": "qfq",
    }
    assert list(df["日期"]) == ["2024-01-02"]


@pytest.mark.asyncio
async def test_get_indicator_passes_symbol(monkeypatch) -> None:
    captured: dict = {}

    def _stub(**kwargs):
        captured.update(kwargs)
        return pd.DataFrame(
            {"数据日期": ["2024-12-31"], "PE(TTM)": [20.0], "市净率": [3.0], "总市值": [1e12]}
        )

    monkeypatch.setattr(ak_mod.ak, "stock_value_em", _stub)

    client = AkshareClient()
    df = await client.get_indicator("600519")

    assert captured == {"symbol": "600519"}
    assert df.iloc[0]["PE(TTM)"] == 20.0


@pytest.mark.asyncio
async def test_get_spot_returns_df(monkeypatch) -> None:
    df = pd.DataFrame({"代码": ["600519"], "最新价": [1600.0], "涨跌幅": [1.5], "成交量": [1000]})
    monkeypatch.setattr(ak_mod.ak, "stock_zh_a_spot_em", lambda: df)

    client = AkshareClient()
    result = await client.get_spot()

    assert list(result["代码"]) == ["600519"]
