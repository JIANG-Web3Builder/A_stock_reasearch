from __future__ import annotations

import urllib.request
from typing import Any

import pandas as pd
from mootdx.quotes import Quotes

from .common import get_prefix, normalize_code, to_float

KLINE_CATEGORY_MAP = {
    "day": 4,
    "week": 5,
    "month": 6,
    "1m": 7,
    "5m": 8,
    "15m": 9,
    "30m": 10,
    "60m": 11,
}


class MarketClient:
    def __init__(self) -> None:
        self.client = Quotes.factory(market="std")

    def kline(self, code: str, category: int | str = 4, offset: int = 300) -> pd.DataFrame:
        stock_code = normalize_code(code)
        actual_category = KLINE_CATEGORY_MAP.get(category, category) if isinstance(category, str) else category
        return self.client.bars(symbol=stock_code, category=actual_category, offset=offset)

    def quotes(self, codes: list[str]) -> pd.DataFrame:
        normalized = [normalize_code(code) for code in codes]
        return self.client.quotes(symbol=normalized)

    def transactions(self, code: str, trade_date: str) -> pd.DataFrame:
        stock_code = normalize_code(code)
        compact_date = trade_date.replace("-", "")
        return self.client.transaction(symbol=stock_code, date=compact_date)

    def finance(self, code: str) -> dict[str, Any]:
        stock_code = normalize_code(code)
        return dict(self.client.finance(symbol=stock_code))

    def f10(self, code: str, name: str) -> str:
        stock_code = normalize_code(code)
        return self.client.F10(symbol=stock_code, name=name)

    def f10_all(self, code: str) -> dict[str, str]:
        categories = [
            "最新提示",
            "公司概况",
            "财务分析",
            "股东研究",
            "股本结构",
            "资本运作",
            "业内点评",
            "行业分析",
            "公司大事",
        ]
        return {category: self.f10(code, category) for category in categories}


def tencent_quote(codes: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [normalize_code(code) for code in codes]
    prefixed = [f"{get_prefix(code)}{code}" for code in normalized]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    result: dict[str, dict[str, Any]] = {}
    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        values = line.split('"')[1].split("~")
        if len(values) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name": values[1],
            "price": to_float(values[3]),
            "last_close": to_float(values[4]),
            "open": to_float(values[5]),
            "change_amt": to_float(values[31]),
            "change_pct": to_float(values[32]),
            "high": to_float(values[33]),
            "low": to_float(values[34]),
            "amount_wan": to_float(values[37]),
            "turnover_pct": to_float(values[38]),
            "pe_ttm": to_float(values[39]),
            "amplitude_pct": to_float(values[43]),
            "mcap_yi": to_float(values[44]),
            "float_mcap_yi": to_float(values[45]),
            "pb": to_float(values[46]),
            "limit_up": to_float(values[47]),
            "limit_down": to_float(values[48]),
            "vol_ratio": to_float(values[49]),
            "pe_static": to_float(values[52]),
        }
    return result
