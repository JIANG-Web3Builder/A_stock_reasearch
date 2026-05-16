from __future__ import annotations

import math
from typing import Any

from .market import tencent_quote
from .research import consensus_eps
from .common import normalize_code


def forward_pe(price: float, eps_forecast: float) -> float:
    if eps_forecast <= 0:
        return float("inf")
    return price / eps_forecast


def pe_digestion(current_pe: float, cagr: float, target_pe: float = 30) -> float:
    if current_pe <= target_pe:
        return 0.0
    if cagr <= 0:
        return float("inf")
    return math.log(current_pe / target_pe) / math.log(1 + cagr)


def calc_peg(pe: float, cagr: float) -> float:
    if cagr <= 0:
        return float("inf")
    return pe / (cagr * 100)


def full_valuation(code: str) -> dict[str, Any]:
    stock_code = normalize_code(code)
    quote = tencent_quote([stock_code]).get(stock_code, {})
    eps_data = consensus_eps(stock_code)
    current_year = eps_data.get("current_year")
    next_year = eps_data.get("next_year")

    eps_cur = current_year.get("avg") if current_year else None
    eps_next = next_year.get("avg") if next_year else None
    price = quote.get("price", 0)
    pe_fwd = forward_pe(price, eps_cur) if eps_cur else float("inf")
    cagr = (eps_next / eps_cur - 1) if eps_cur and eps_next else 0
    peg = calc_peg(pe_fwd, cagr) if cagr > 0 else float("inf")
    digest_years = pe_digestion(pe_fwd, cagr) if pe_fwd != float("inf") else float("inf")

    return {
        "code": stock_code,
        "name": quote.get("name"),
        "price": price,
        "mcap_yi": quote.get("mcap_yi"),
        "pe_ttm": quote.get("pe_ttm"),
        "pb": quote.get("pb"),
        "eps_cur": eps_cur,
        "eps_next": eps_next,
        "pe_fwd": round(pe_fwd, 2) if pe_fwd != float("inf") else None,
        "cagr_pct": round(cagr * 100, 2) if cagr else None,
        "peg": round(peg, 2) if peg != float("inf") else None,
        "digest_years": round(digest_years, 2) if digest_years != float("inf") else None,
        "analyst_count": eps_data.get("analyst_count", 0),
        "forecast_records": eps_data.get("records", []),
        "quote": quote,
    }
