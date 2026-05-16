# A-share Research Toolkit

这是一个面向 A 股研究的本地 Python 工具项目，用于统一整理多数据源的行情、研报、新闻、公告、基础面、信号与补充外部接口。

## 已整理的数据源

- mootdx
- 腾讯财经
- akshare / 东方财富
- 同花顺
- 百度股市通
- 巨潮资讯
- tushare
- yfinance

## 目录结构

```text
src/ashare_research/
  common.py
  market.py
  research.py
  news.py
  fundamentals.py
  announcements.py
  signals.py
  valuation.py
  snapshot.py
  external.py
scripts/
  collect_stock_snapshot.py
  market_signal_report.py
```

## 外部接口

`src/ashare_research/external.py` 中包含：

- `to_tushare_code`
- `make_tushare_client`
- `tushare_daily`
- `yfinance_history`
- `yfinance_options_chain`
- `capm_regression`

## 使用说明

### 安装依赖

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### 配置 Tushare

```powershell
$env:TUSHARE_TOKEN="your_token"
```

### 运行脚本

```powershell
.\.venv\Scripts\python scripts\collect_stock_snapshot.py 688017 --date 2026-05-15
.\.venv\Scripts\python scripts\market_signal_report.py --date 2026-05-15
```

## 本次验证

- `tushare_daily` 已实际跑通
- `yfinance_history` 已实际跑通
- `yfinance_options_chain` 已实际跑通
- `capm_regression` 已实际跑通

注：`yfinance` 直连会遇到 Yahoo 限流，使用本地代理后验证通过。
