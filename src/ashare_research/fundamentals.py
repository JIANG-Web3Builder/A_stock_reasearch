from __future__ import annotations

import akshare as ak
import pandas as pd
from mootdx.quotes import Quotes

from .common import make_session, normalize_code


def _scalar(value):
    if isinstance(value, pd.Series):
        return value.iloc[0] if not value.empty else None
    return value


class FundamentalsClient:
    def __init__(self) -> None:
        self.client = Quotes.factory(market="std")

    def finance_snapshot(self, code: str) -> dict:
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


def stock_individual_info(code: str):
    stock_code = normalize_code(code)
    market_code = 1 if stock_code.startswith("6") else 0
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": (
            "f120,f121,f122,f174,f175,f59,f163,f43,f57,f58,f169,f170,f46,f44,f51,f168,f47,"
            "f164,f116,f60,f45,f52,f50,f48,f167,f117,f71,f161,f49,f530,f135,f136,f137,f138,"
            "f139,f141,f142,f144,f145,f147,f148,f140,f143,f146,f149,f55,f62,f162,f92,f173,f104,"
            "f105,f84,f85,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f107,f111,f86,f177,f78,"
            "f110,f262,f263,f264,f267,f268,f255,f256,f257,f258,f127,f199,f128,f198,f259,f260,f261,"
            "f171,f277,f278,f279,f288,f152,f250,f251,f252,f253,f254,f269,f270,f271,f272,f273,f274,"
            "f275,f276,f265,f266,f289,f290,f286,f285,f292,f293,f294,f295,f43"
        ),
        "secid": f"{market_code}.{stock_code}",
    }
    session = make_session({"Referer": "https://quote.eastmoney.com/"})
    rows = []
    try:
        response = session.get("https://push2.eastmoney.com/api/qt/stock/get", params=params, timeout=15)
        response.raise_for_status()
        data_json = response.json()
        payload = data_json.get("data") or {}
        code_name_map = {
            "f57": "股票代码",
            "f58": "股票简称",
            "f84": "总股本",
            "f85": "流通股",
            "f127": "行业",
            "f116": "总市值",
            "f117": "流通市值",
            "f189": "上市时间",
            "f43": "最新",
        }
        for key, label in code_name_map.items():
            if key in payload:
                rows.append({"item": label, "value": payload.get(key)})
    except Exception:
        from .market import tencent_quote

        quote = tencent_quote([stock_code]).get(stock_code, {})
        finance = {}
        try:
            finance = dict(Quotes.factory(market="std").finance(symbol=stock_code))
        except Exception:
            finance = {}
        fallback_map = {
            "股票代码": stock_code,
            "股票简称": quote.get("name"),
            "总股本": _scalar(finance.get("zongguben")),
            "流通股": _scalar(finance.get("liutongguben")),
            "总市值": quote.get("mcap_yi"),
            "流通市值": quote.get("float_mcap_yi"),
            "最新": quote.get("price"),
        }
        for label, value in fallback_map.items():
            if value not in (None, ""):
                rows.append({"item": label, "value": value})
    return pd.DataFrame(rows, columns=["item", "value"])
