from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
REPORT_DIR = DATA_DIR / "reports"
SNAPSHOT_DIR = DATA_DIR / "snapshots"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

for folder in (DATA_DIR, CACHE_DIR, REPORT_DIR, SNAPSHOT_DIR):
    folder.mkdir(parents=True, exist_ok=True)


def normalize_code(code: str) -> str:
    raw = str(code).strip().upper()
    if raw.startswith(("SH", "SZ", "BJ")):
        raw = raw[2:]
    if raw.endswith((".SH", ".SZ", ".BJ")):
        raw = raw.split(".", 1)[0]
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"invalid stock code: {code}")
    return digits


def get_prefix(code: str) -> str:
    value = normalize_code(code)
    if value.startswith(("6", "9")):
        return "sh"
    if value.startswith("8"):
        return "bj"
    return "sz"


def get_cninfo_market(code: str) -> str:
    value = normalize_code(code)
    if value.startswith("6"):
        return "沪市"
    if value.startswith("8"):
        return "北交所"
    return "深市"


def make_session(headers: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    session.headers.update(merged)
    return session


def to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "--"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    if value in (None, "", "--"):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def dataframe_to_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    clean = df.where(pd.notnull(df), None)
    return clean.to_dict(orient="records")


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> Path:
    ensure_parent(path)
    path.write_text(
        json.dumps(to_serializable(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def to_serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.DataFrame):
        return dataframe_to_records(value)
    if isinstance(value, pd.Series):
        return value.where(pd.notnull(value), None).to_dict()
    if isinstance(value, dict):
        return {str(k): to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_serializable(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value
