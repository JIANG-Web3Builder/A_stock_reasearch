from __future__ import annotations

from collections import Counter
from datetime import date as date_cls
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd
import requests

from .common import CACHE_DIR, dataframe_to_records, make_session, normalize_code, to_float
from .fundamentals import stock_individual_info

HSGT_HEADERS = {
    "Host": "data.hexin.cn",
    "Referer": "https://data.hexin.cn/",
}
_BAIDU_PAE_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


def _fallback_concept_blocks(code: str) -> dict[str, Any]:
    result = {"industry": [], "concept": [], "region": [], "concept_tags": []}
    try:
        df = stock_individual_info(code)
        if not df.empty and {"item", "value"}.issubset(df.columns):
            mapping = dict(zip(df["item"], df["value"]))
            industry = mapping.get("行业")
            if industry:
                result["industry"].append({"name": str(industry), "change_pct": "", "desc": "akshare fallback"})
    except Exception:
        pass
    return result


def ths_hot_reason(date: str | None = None) -> pd.DataFrame:
    actual_date = date or date_cls.today().strftime("%Y-%m-%d")
    url = (
        f"http://zx.10jqka.com.cn/event/api/getharden/"
        f"date/{actual_date}/orderby/date/orderway/desc/charset/GBK/"
    )
    session = make_session()
    response = session.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("errocode", 0) != 0:
        raise RuntimeError(f"同花顺热点错误: {data.get('errormsg', '')}")
    rows = data.get("data") or []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    rename_map = {
        "name": "名称",
        "code": "代码",
        "reason": "题材归因",
        "close": "收盘价",
        "zhangdie": "涨跌额",
        "zhangfu": "涨幅%",
        "huanshou": "换手率%",
        "chengjiaoe": "成交额",
        "chengjiaoliang": "成交量",
        "ddejingliang": "大单净量",
        "market": "市场",
    }
    return df.rename(columns=rename_map)


def analyze_hot_topics(date: str | None = None, top_n: int = 10) -> list[dict[str, Any]]:
    df = ths_hot_reason(date)
    counter: Counter[str] = Counter()
    if df.empty or "题材归因" not in df.columns:
        return []
    for reason in df["题材归因"].dropna():
        tags = [item.strip() for item in str(reason).split("+") if item.strip()]
        counter.update(tags)
    return [{"tag": tag, "count": count} for tag, count in counter.most_common(top_n)]


def hsgt_realtime() -> pd.DataFrame:
    session = make_session(HSGT_HEADERS)
    response = session.get("https://data.hexin.cn/market/hsgtApi/method/dayChart/", timeout=10)
    response.raise_for_status()
    data = response.json()
    times = data.get("time", [])
    hgt = data.get("hgt", [])
    sgt = data.get("sgt", [])
    length = len(times)
    return pd.DataFrame(
        {
            "time": times,
            "hgt_yi": hgt[:length] + [None] * (length - len(hgt)),
            "sgt_yi": sgt[:length] + [None] * (length - len(sgt)),
        }
    )


def northbound_cache_path() -> Path:
    path = CACHE_DIR / "northbound_daily.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def save_northbound_snapshot(trade_date: str, hgt: float, sgt: float) -> Path:
    path = northbound_cache_path()
    rows: dict[str, str] = {}
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        for line in text.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) == 3:
                rows[parts[0]] = line
    rows[trade_date] = f"{trade_date},{hgt},{sgt}"
    with path.open("w", encoding="utf-8") as handle:
        handle.write("date,hgt,sgt\n")
        for item_date in sorted(rows.keys()):
            handle.write(rows[item_date] + "\n")
    return path


def load_northbound_history(n: int = 20) -> pd.DataFrame:
    path = northbound_cache_path()
    if not path.exists():
        return pd.DataFrame(columns=["date", "hgt", "sgt"])
    df = pd.read_csv(path)
    return df.tail(n)


def capture_northbound_close(trade_date: str | None = None) -> dict[str, Any]:
    actual_date = trade_date or date_cls.today().strftime("%Y-%m-%d")
    df = hsgt_realtime()
    if df.empty or df.dropna().empty:
        return {"date": actual_date, "saved": False, "records": 0}
    last = df.dropna().iloc[-1]
    path = save_northbound_snapshot(actual_date, to_float(last["hgt_yi"]), to_float(last["sgt_yi"]))
    return {
        "date": actual_date,
        "saved": True,
        "records": len(df),
        "hgt_yi": to_float(last["hgt_yi"]),
        "sgt_yi": to_float(last["sgt_yi"]),
        "path": str(path),
    }


def baidu_concept_blocks(code: str) -> dict[str, Any]:
    stock_code = normalize_code(code)
    session = make_session(_BAIDU_PAE_HEADERS)
    candidates = [
        {"stock": stock_code},
        {"stock": f"ab-{stock_code}"},
        {"code": stock_code, "market": "ab", "typeCode": "all", "finClientType": "pc"},
    ]
    data: dict[str, Any] | None = None
    for params in candidates:
        response = session.get("https://finance.pae.baidu.com/api/getrelatedblock", params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("ResultCode", -1)) == "0" and payload.get("Result"):
            data = payload
            break
    if not data:
        return _fallback_concept_blocks(stock_code)

    result = {"industry": [], "concept": [], "region": [], "concept_tags": []}
    for block in data.get("Result", []):
        block_type = block.get("type", "")
        for item in block.get("list", []):
            entry = {
                "name": item.get("name", ""),
                "change_pct": item.get("increase", ""),
                "desc": item.get("desc", ""),
            }
            if "行业" in block_type:
                result["industry"].append(entry)
            elif "概念" in block_type:
                result["concept"].append(entry)
                result["concept_tags"].append(entry["name"])
            elif "地域" in block_type:
                result["region"].append(entry)
    if not result["industry"] and not result["concept"] and not result["region"]:
        fallback = _fallback_concept_blocks(stock_code)
        if fallback["industry"]:
            return fallback
    return result


def baidu_fund_flow_realtime(code: str, trade_date: str) -> list[dict[str, Any]]:
    stock_code = normalize_code(code)
    compact_date = trade_date.replace("-", "")
    session = make_session(_BAIDU_PAE_HEADERS)
    url = (
        f"https://finance.pae.baidu.com/vapi/v1/fundflow"
        f"?code={stock_code}&market=ab&date={compact_date}&finClientType=pc"
    )
    response = session.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if str(data.get("ResultCode", -1)) != "0":
        return []
    result = data.get("Result") or {}
    if not isinstance(result, dict):
        return []
    raw = result.get("update_data", "")
    if not raw:
        return []
    rows: list[dict[str, Any]] = []
    for segment in raw.split(";"):
        parts = segment.split(",")
        if len(parts) >= 9:
            rows.append(
                {
                    "time": parts[0],
                    "mainForce": to_float(parts[2]),
                    "retail": to_float(parts[3]),
                    "super": to_float(parts[4]),
                    "large": to_float(parts[5]),
                    "price": to_float(parts[8]),
                }
            )
    return rows


def baidu_fund_flow_history(code: str, days: int = 20) -> list[dict[str, Any]]:
    stock_code = normalize_code(code)
    session = make_session(_BAIDU_PAE_HEADERS)
    url = (
        f"https://finance.pae.baidu.com/vapi/v1/fundsortlist"
        f"?code={stock_code}&market=ab&pn=0&rn={days}&finClientType=pc"
    )
    response = session.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    if str(data.get("ResultCode", -1)) != "0":
        return []
    result = data.get("Result") or {}
    if not isinstance(result, dict):
        return []
    rows: list[dict[str, Any]] = []
    for item in result.get("list", []):
        rows.append(
            {
                "date": item.get("showtime", ""),
                "close": item.get("closepx", ""),
                "change_pct": item.get("ratio", ""),
                "superNetIn": item.get("superNetIn", ""),
                "largeNetIn": item.get("largeNetIn", ""),
                "mediumNetIn": item.get("mediumNetIn", ""),
                "littleNetIn": item.get("littleNetIn", ""),
                "mainIn": item.get("extMainIn", ""),
            }
        )
    return rows


def dragon_tiger_board(code: str, trade_date: str, look_back: int = 30) -> dict[str, Any]:
    stock_code = normalize_code(code)
    start = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)
    start_str = start.strftime("%Y%m%d")
    end_str = trade_date.replace("-", "")
    records: list[dict[str, Any]] = []
    try:
        df = ak.stock_lhb_detail_em(start_date=start_str, end_date=end_str)
        if not df.empty:
            df_stock = df[df["代码"] == stock_code]
            for _, row in df_stock.iterrows():
                records.append(
                    {
                        "date": str(row.get("日期", "")),
                        "reason": row.get("解读", ""),
                        "net_buy": row.get("龙虎榜净买额", 0),
                        "turnover": row.get("换手率", 0),
                    }
                )
    except Exception:
        pass

    seats = {"buy": [], "sell": []}
    if records:
        latest_date = records[0]["date"].replace("-", "")[:8]
        for flag, key in (("买入", "buy"), ("卖出", "sell")):
            try:
                df_detail = ak.stock_lhb_stock_detail_em(symbol=stock_code, date=latest_date, flag=flag)
                if not df_detail.empty:
                    for _, row in df_detail.head(5).iterrows():
                        seats[key].append(
                            {
                                "name": row.get("营业部名称", ""),
                                "buy_amt": row.get("买入额", 0),
                                "sell_amt": row.get("卖出额", 0),
                                "net": row.get("净额", 0),
                            }
                        )
            except Exception:
                pass

    institution: dict[str, Any] = {}
    try:
        df_inst = ak.stock_lhb_jgmmtj_em(symbol=stock_code)
        if not df_inst.empty:
            row = df_inst.iloc[0]
            institution = {
                "buy_count": row.get("买入机构数", 0),
                "sell_count": row.get("卖出机构数", 0),
                "net_amount": row.get("机构净买入额", 0),
            }
    except Exception:
        pass
    return {"records": records, "seats": seats, "institution": institution}


def lockup_expiry(code: str, trade_date: str, forward_days: int = 90) -> dict[str, Any]:
    stock_code = normalize_code(code)
    history: list[dict[str, Any]] = []
    try:
        df = ak.stock_restricted_release_queue_em(symbol=stock_code)
        if not df.empty:
            for _, row in df.head(15).iterrows():
                history.append(
                    {
                        "date": str(row.get("解禁时间", "")),
                        "type": row.get("限售股类型", ""),
                        "shares": row.get("解禁数量", 0),
                        "ratio": row.get("实际解禁市值占总市值比例", 0),
                    }
                )
    except Exception:
        pass

    upcoming: list[dict[str, Any]] = []
    try:
        end_date = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)
        _ = end_date.strftime("%Y%m%d")
        today_str = trade_date.replace("-", "")
        df = ak.stock_restricted_release_detail_em(date=today_str)
        if not df.empty:
            df_stock = df[df["股票代码"] == stock_code]
            for _, row in df_stock.iterrows():
                upcoming.append(
                    {
                        "date": str(row.get("解禁日期", "")),
                        "type": row.get("限售股类型", ""),
                        "shares": row.get("解禁数量", 0),
                        "float_ratio": row.get("占流通股比例", 0),
                    }
                )
    except Exception:
        pass
    return {"history": history, "upcoming": upcoming}


def industry_comparison(top_n: int = 20) -> dict[str, Any]:
    df = ak.stock_board_industry_summary_ths()
    if df.empty:
        return {"top": [], "bottom": [], "total": 0}
    rows: list[dict[str, Any]] = []
    for index, row in df.iterrows():
        rows.append(
            {
                "rank": index + 1,
                "name": row.get("板块", ""),
                "change_pct": row.get("涨跌幅", 0),
                "turnover_yi": row.get("总成交额", 0),
                "net_inflow_yi": row.get("净流入", 0) if "净流入" in df.columns else None,
                "up_count": row.get("上涨家数", 0),
                "down_count": row.get("下跌家数", 0),
                "leader": row.get("领涨股", ""),
            }
        )
    return {"top": rows[:top_n], "bottom": rows[-top_n:], "total": len(rows)}


def daily_dragon_tiger(trade_date: str | None = None, min_net_buy: float | None = None) -> dict[str, Any]:
    actual_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    session = make_session({"Referer": "https://data.eastmoney.com/"})
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "filter": f"(TRADE_DATE>='{actual_date}')(TRADE_DATE<='{actual_date}')",
        "pageNumber": "1",
        "pageSize": "500",
        "sortTypes": "-1",
        "sortColumns": "BILLBOARD_NET_AMT",
        "source": "WEB",
        "client": "WEB",
    }
    response = session.get("https://datacenter-web.eastmoney.com/api/data/v1/get", params=params, timeout=15)
    response.raise_for_status()
    data = response.json()
    if not data.get("success") or not data.get("result") or not data["result"].get("data"):
        return {"date": actual_date, "total_records": 0, "stocks": [], "note": "无数据（非交易日或盘后未更新）"}
    rows = data["result"]["data"]
    actual_trade_date = rows[0].get("TRADE_DATE", "")[:10] if rows else actual_date
    stocks: list[dict[str, Any]] = []
    for row in rows:
        net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
        if min_net_buy is not None and net_buy < min_net_buy:
            continue
        stocks.append(
            {
                "code": row.get("SECURITY_CODE", ""),
                "name": row.get("SECURITY_NAME_ABBR", ""),
                "reason": row.get("EXPLANATION", ""),
                "close": row.get("CLOSE_PRICE") or 0,
                "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
                "net_buy_wan": round(net_buy, 1),
                "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
                "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
                "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
            }
        )
    return {"date": actual_trade_date, "total_records": len(stocks), "stocks": stocks}
