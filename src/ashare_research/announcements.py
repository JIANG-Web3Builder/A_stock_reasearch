from __future__ import annotations

import akshare as ak

from .common import normalize_code
from .fundamentals import FundamentalsClient


def cninfo_announcements(code: str):
    stock_code = normalize_code(code)
    return ak.stock_zh_a_disclosure_report_cninfo(symbol=stock_code, market="沪深京")


def f10_notice_summary(code: str) -> str:
    client = FundamentalsClient()
    return client.f10(code, "最新提示")
