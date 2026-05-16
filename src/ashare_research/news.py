from __future__ import annotations

import akshare as ak
import pandas as pd

from .common import normalize_code


def stock_news(code: str) -> pd.DataFrame:
    return ak.stock_news_em(symbol=normalize_code(code))


def cls_telegraph() -> pd.DataFrame:
    return ak.stock_info_global_cls()


def eastmoney_global_news() -> pd.DataFrame:
    return ak.stock_info_global_em()
