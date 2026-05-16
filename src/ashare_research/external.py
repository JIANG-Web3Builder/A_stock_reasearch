from __future__ import annotations

import os
from typing import Any

import pandas as pd

from .common import normalize_code


class MissingTushareTokenError(RuntimeError):
    pass


class MissingExternalDependencyError(RuntimeError):
    pass


def _import_tushare():
    try:
        import tushare as ts
    except ImportError as exc:
        raise MissingExternalDependencyError("tushare is required for tushare integrations") from exc
    return ts


def _import_yfinance():
    try:
        import yfinance as yf
    except ImportError as exc:
        raise MissingExternalDependencyError("yfinance is required for yfinance integrations") from exc
    return yf


def _import_statsmodels_api():
    try:
        import statsmodels.api as sm
    except ImportError as exc:
        raise MissingExternalDependencyError("statsmodels is required for CAPM regression") from exc
    return sm


def _apply_proxy(proxy: str | None = None) -> None:
    if not proxy:
        return
    os.environ["http_proxy"] = proxy
    os.environ["https_proxy"] = proxy


def to_tushare_code(code: str) -> str:
    stock_code = normalize_code(code)
    if stock_code.startswith(("6", "9")):
        market = "SH"
    elif stock_code.startswith("8"):
        market = "BJ"
    else:
        market = "SZ"
    return f"{stock_code}.{market}"


def make_tushare_client(token: str | None = None, proxy: str | None = None):
    _apply_proxy(proxy)
    actual_token = token or os.getenv("TUSHARE_TOKEN")
    if not actual_token:
        raise MissingTushareTokenError("TUSHARE_TOKEN is required")
    ts = _import_tushare()
    return ts.pro_api(actual_token)


def tushare_daily(
    code: str | None = None,
    ts_code: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    token: str | None = None,
    proxy: str | None = None,
) -> pd.DataFrame:
    actual_code = ts_code or (to_tushare_code(code) if code else None)
    if not actual_code:
        raise ValueError("code or ts_code is required")
    client = make_tushare_client(token=token, proxy=proxy)
    df = client.daily(ts_code=actual_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        return pd.DataFrame()
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def yfinance_history(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
    auto_adjust: bool = False,
    proxy: str | None = None,
) -> pd.DataFrame:
    _apply_proxy(proxy)
    yf = _import_yfinance()
    df = yf.download(
        ticker,
        start=start_date,
        end=end_date,
        interval=interval,
        auto_adjust=auto_adjust,
        progress=False,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df.reset_index()


def yfinance_options_chain(ticker: str, proxy: str | None = None) -> pd.DataFrame:
    _apply_proxy(proxy)
    yf = _import_yfinance()
    ticker_client = yf.Ticker(ticker)
    expiry_dates = ticker_client.options or []
    frames: list[pd.DataFrame] = []
    for expiry in expiry_dates:
        chain = ticker_client.option_chain(expiry)
        call_df = chain.calls.assign(option_type="call")
        put_df = chain.puts.assign(option_type="put")
        merged = pd.concat([call_df, put_df], ignore_index=True)
        merged["expiration"] = pd.to_datetime(expiry)
        frames.append(merged)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def capm_regression(
    ticker: str,
    benchmark: str = "^GSPC",
    start_date: str | None = None,
    end_date: str | None = None,
    proxy: str | None = None,
) -> dict[str, Any]:
    sm = _import_statsmodels_api()
    stock = yfinance_history(ticker, start_date=start_date, end_date=end_date, proxy=proxy)
    market = yfinance_history(benchmark, start_date=start_date, end_date=end_date, proxy=proxy)
    if stock.empty or market.empty:
        raise ValueError("empty history returned from yfinance")

    stock_close = stock[["Date", "Close"]].copy()
    market_close = market[["Date", "Close"]].copy()
    stock_close["Stock"] = stock_close["Close"].pct_change()
    market_close["Market"] = market_close["Close"].pct_change()

    data = pd.merge(stock_close[["Date", "Stock"]], market_close[["Date", "Market"]], on="Date", how="inner")
    data = data.dropna().reset_index(drop=True)
    if data.empty:
        raise ValueError("insufficient overlap for CAPM regression")

    X = sm.add_constant(data["Market"])
    y = data["Stock"]
    model = sm.OLS(y, X).fit()
    alpha = float(model.params["const"])
    beta = float(model.params["Market"])

    return {
        "ticker": ticker,
        "benchmark": benchmark,
        "start_date": start_date,
        "end_date": end_date,
        "alpha": alpha,
        "beta": beta,
        "r_squared": float(model.rsquared),
        "observations": int(len(data)),
    }
