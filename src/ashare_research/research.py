from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

import akshare as ak
import requests
import pandas as pd

from .common import REPORT_DIR, dataframe_to_records, make_session, normalize_code, to_float, to_int

REPORT_API = "https://reportapi.eastmoney.com/report/list"
PDF_TPL = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://data.eastmoney.com/",
}
IWENCAI_BASE = os.environ.get("IWENCAI_BASE_URL", "https://openapi.iwencai.com")
IWENCAI_KEY = os.environ.get("IWENCAI_API_KEY", "")


class MissingIwenCaiKeyError(RuntimeError):
    pass


def eastmoney_reports(code: str, max_pages: int = 5) -> list[dict[str, Any]]:
    stock_code = normalize_code(code)
    session = make_session(EASTMONEY_HEADERS)
    all_records: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*",
            "pageSize": "100",
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": "2000-01-01",
            "endTime": "2030-01-01",
            "pageNo": str(page),
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": stock_code,
            "rcode": "",
            "p": str(page),
            "pageNum": str(page),
            "pageNumber": str(page),
        }
        response = session.get(REPORT_API, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        rows = data.get("data") or []
        if not rows:
            break
        all_records.extend(rows)
        if page >= (data.get("TotalPage", 1) or 1):
            break
        time.sleep(0.3)
    return all_records


def download_pdf(record: dict[str, Any], target_dir: str | Path | None = None) -> Path | None:
    info_code = record.get("infoCode", "")
    if not info_code:
        return None
    date = str(record.get("publishDate") or "")[:10]
    org = str(record.get("orgSName") or "未知")
    title = re.sub(r'[\\/:*?"<>|]', "_", str(record.get("title") or ""))[:80]
    filename = f"{date}_{org}_{title}.pdf"
    target_root = Path(target_dir) if target_dir else REPORT_DIR
    target = target_root / filename
    if target.exists():
        return target
    url = PDF_TPL.format(info_code=info_code)
    response = requests.get(url, headers=EASTMONEY_HEADERS, timeout=60)
    if response.status_code == 200 and len(response.content) >= 1024:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target
    return None


def profit_forecast(code: str, indicator: str = "预测年报每股收益") -> pd.DataFrame:
    stock_code = normalize_code(code)
    return ak.stock_profit_forecast_ths(symbol=stock_code, indicator=indicator)


def consensus_eps(code: str) -> dict[str, Any]:
    df = profit_forecast(code, indicator="预测年报每股收益")
    if df.empty:
        return {"records": [], "current_year": None, "next_year": None, "analyst_count": 0}

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        records.append(
            {
                "year": str(row.get("年度", "")),
                "analyst_count": to_int(row.get("预测机构数", 0)),
                "min": to_float(row.get("最小值", 0)),
                "avg": to_float(row.get("均值", 0)),
                "max": to_float(row.get("最大值", 0)),
                "industry_avg": to_float(row.get("行业平均数", 0)),
            }
        )

    years_sorted = sorted(records, key=lambda item: item["year"])
    current_year = years_sorted[0] if years_sorted else None
    next_year = years_sorted[1] if len(years_sorted) > 1 else None
    analyst_count = current_year["analyst_count"] if current_year else 0
    return {
        "records": records,
        "current_year": current_year,
        "next_year": next_year,
        "analyst_count": analyst_count,
    }


def _claw_headers(call_type: str = "normal") -> dict[str, str]:
    return {
        "X-Claw-Call-Type": call_type,
        "X-Claw-Skill-Id": "report-search",
        "X-Claw-Skill-Version": "2.0.0",
        "X-Claw-Plugin-Id": "none",
        "X-Claw-Plugin-Version": "none",
        "X-Claw-Trace-Id": secrets.token_hex(32),
    }


def _require_iwencai_key() -> None:
    if not IWENCAI_KEY:
        raise MissingIwenCaiKeyError("IWENCAI_API_KEY is required for iwencai endpoints")


def iwencai_search(query: str, channel: str = "report", size: int = 50) -> list[dict[str, Any]]:
    _require_iwencai_key()
    headers = {
        "Authorization": f"Bearer {IWENCAI_KEY}",
        "Content-Type": "application/json",
        **_claw_headers(),
    }
    payload = {
        "channels": [channel],
        "app_id": "AIME_SKILL",
        "query": query,
        "size": size,
    }
    response = requests.post(
        f"{IWENCAI_BASE}/v1/comprehensive/search",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"iwencai HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if data.get("status_code", 0) != 0:
        raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
    return data.get("data") or []


def iwencai_query(query: str, page: int = 1, limit: int = 50) -> list[dict[str, Any]]:
    _require_iwencai_key()
    headers = {
        "Authorization": f"Bearer {IWENCAI_KEY}",
        "Content-Type": "application/json",
        **_claw_headers(),
    }
    payload = {
        "query": query,
        "page": str(page),
        "limit": str(limit),
        "is_cache": "1",
        "expand_index": "true",
    }
    response = requests.post(
        f"{IWENCAI_BASE}/v1/query2data",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"iwencai HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if data.get("status_code", 0) != 0:
        raise RuntimeError(f"iwencai error: {data.get('status_msg', '')}")
    return data.get("datas") or []


def dedup_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for article in articles:
        uid = article.get("uid", "") or f"{article.get('title', '')}|{article.get('publish_date', '')}"
        score = to_float(article.get("score", 0))
        if uid not in best or score > to_float(best[uid].get("score", 0)):
            best[uid] = article
    return sorted(best.values(), key=lambda item: item.get("publish_date", ""), reverse=True)


def topic_report_search(queries: list[str], size: int = 50) -> list[dict[str, Any]]:
    seen_uids: set[str] = set()
    all_articles: list[dict[str, Any]] = []
    for query in queries:
        articles = iwencai_search(query, channel="report", size=size)
        for article in articles:
            uid = article.get("uid", "")
            if uid and uid in seen_uids:
                continue
            if uid:
                seen_uids.add(uid)
            all_articles.append(article)
    return dedup_articles(all_articles)
