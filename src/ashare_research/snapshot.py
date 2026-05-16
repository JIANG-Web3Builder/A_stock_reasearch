from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .announcements import cninfo_announcements, f10_notice_summary
from .common import SNAPSHOT_DIR, dataframe_to_records, normalize_code, write_json
from .fundamentals import FundamentalsClient, stock_individual_info
from .market import MarketClient, tencent_quote
from .news import stock_news
from .research import consensus_eps, eastmoney_reports
from .signals import baidu_concept_blocks, baidu_fund_flow_history, dragon_tiger_board, lockup_expiry
from .valuation import full_valuation


def _safe_call(errors: dict[str, str], name: str, func, default):
    try:
        return func()
    except Exception as exc:
        errors[name] = f"{type(exc).__name__}: {exc}"
        return default


def build_stock_snapshot(code: str, trade_date: str | None = None) -> dict[str, Any]:
    stock_code = normalize_code(code)
    actual_trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    market_client = MarketClient()
    fundamentals_client = FundamentalsClient()
    errors: dict[str, str] = {}

    quote = _safe_call(errors, "quote", lambda: tencent_quote([stock_code]).get(stock_code, {}), {})
    reports = _safe_call(errors, "reports", lambda: eastmoney_reports(stock_code, max_pages=2), [])
    result = {
        "code": stock_code,
        "trade_date": actual_trade_date,
        "quote": quote,
        "valuation": _safe_call(errors, "valuation", lambda: full_valuation(stock_code), {}),
        "consensus_eps": _safe_call(errors, "consensus_eps", lambda: consensus_eps(stock_code), {}),
        "reports": reports[:30],
        "news": _safe_call(errors, "news", lambda: dataframe_to_records(stock_news(stock_code).head(20)), []),
        "concept_blocks": _safe_call(errors, "concept_blocks", lambda: baidu_concept_blocks(stock_code), {"industry": [], "concept": [], "region": [], "concept_tags": []}),
        "fund_flow": _safe_call(errors, "fund_flow", lambda: baidu_fund_flow_history(stock_code, days=20), []),
        "dragon_tiger": _safe_call(errors, "dragon_tiger", lambda: dragon_tiger_board(stock_code, actual_trade_date), {"records": [], "seats": {"buy": [], "sell": []}, "institution": {}}),
        "lockup": _safe_call(errors, "lockup", lambda: lockup_expiry(stock_code, actual_trade_date), {"history": [], "upcoming": []}),
        "cninfo_announcements": _safe_call(errors, "cninfo_announcements", lambda: dataframe_to_records(cninfo_announcements(stock_code).head(20)), []),
        "f10_notice_summary": _safe_call(errors, "f10_notice_summary", lambda: f10_notice_summary(stock_code), ""),
        "finance_snapshot": _safe_call(errors, "finance_snapshot", lambda: fundamentals_client.finance_snapshot(stock_code), {}),
        "f10": _safe_call(errors, "f10", lambda: fundamentals_client.f10_all(stock_code), {}),
        "individual_info": _safe_call(errors, "individual_info", lambda: dataframe_to_records(stock_individual_info(stock_code)), []),
        "kline_daily": _safe_call(errors, "kline_daily", lambda: dataframe_to_records(market_client.kline(stock_code, category="day", offset=120).tail(120)), []),
        "errors": errors,
    }
    return result


def save_stock_snapshot(code: str, trade_date: str | None = None, output_dir: str | Path | None = None) -> Path:
    actual_trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    stock_code = normalize_code(code)
    root = Path(output_dir) if output_dir else SNAPSHOT_DIR
    path = root / f"{stock_code}_{actual_trade_date}.json"
    payload = build_stock_snapshot(stock_code, actual_trade_date)
    return write_json(path, payload)
