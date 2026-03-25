"""Fetch upcoming 30-day earnings reports (財報) and investor conferences (法說會)
for TWSE/TPEX (Taiwan) and major US stocks.

Data sources:
- Taiwan 法說會: MOPS (公開資訊觀測站)
- US Earnings:   yfinance
"""

import csv
import io
import os
import re
import sys
from datetime import datetime, timedelta

import urllib3
import requests
import yfinance as yf
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

OUTPUT_FILE = "upcoming_earnings.csv"
CSV_HEADERS = ["類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"]

# 監控的美股清單：從 raw_conceptstock_company_metadata.csv 動態載入
# 來源：wenchiehlee-investment/ConceptStocks
_METADATA_CSV_PATHS = [
    "../ConceptStocks/raw_conceptstock_company_metadata.csv",  # 本機開發
    "raw_conceptstock_company_metadata.csv",                   # CI 環境（sync 後）
]

def _load_us_watchlist() -> dict[str, str]:
    """從 raw_conceptstock_company_metadata.csv 載入 {Ticker: 公司名稱}，排除無上市 ticker（'-'）。"""
    for path in _METADATA_CSV_PATHS:
        if not os.path.exists(path):
            continue
        result = {}
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("Ticker", "").strip()
                name   = row.get("公司名稱", "").strip()
                if ticker and ticker != "-":
                    result[ticker] = name
        print(f"  [US_WATCHLIST] Loaded {len(result)} tickers from {path}")
        return result
    print("  [US_WATCHLIST] raw_conceptstock_company_metadata.csv not found, using empty list.")
    return {}

US_WATCHLIST = _load_us_watchlist()

WATCHLIST_CSV      = "StockID_TWSE_TPEX.csv"        # 完整觀察名單
WATCHLIST_FOCUS_CSV = "StockID_TWSE_TPEX_focus.csv"  # 專注名單


def _load_tw_watchlist(csv_path: str) -> dict[str, str]:
    """從 CSV（代號,名稱）載入台股清單，轉成 {symbol.TW: name} dict。"""
    watchlist: dict[str, str] = {}
    if not os.path.exists(csv_path):
        print(f"  Warning: {csv_path} not found, skipping Taiwan watchlist.")
        return watchlist
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row.get("代號", "").strip()
            name = row.get("名稱", "").strip()
            if code and code != "0000":   # 跳過指數列
                watchlist[f"{code}.TW"] = name
    return watchlist

MOPS_BASE_URL       = "https://mops.twse.com.tw/mops/#/web/t100sb07_1"
MOPS_REDIRECT_URL   = "https://mops.twse.com.tw/mops/api/redirectToOld"


def _date_range_30() -> tuple[datetime, datetime]:
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=30), today + timedelta(days=30)


# ── Taiwan 法說會 (MOPS) ─────────────────────────────────────────────────────

def _parse_mops_company_html(html: str, code: str, name: str,
                              start: datetime, end: datetime) -> list[list]:
    """從單一公司 ajax_t100sb07_1 HTML 擷取落在日期範圍內的法說會事件。"""
    rows = []
    # 找所有 ROC 日期（格式 YYY/MM/DD），出現在「召開法人說明會日期」附近
    date_pattern = re.compile(r"(\d{3}/\d{2}/\d{2})")
    for m in date_pattern.finditer(html):
        date_roc = m.group(1)
        try:
            y, mo, d = date_roc.split("/")
            event_date = datetime(int(y) + 1911, int(mo), int(d))
        except ValueError:
            continue
        if not (start <= event_date <= end):
            continue
        date_str = event_date.strftime("%Y-%m-%d")
        event_name = f"{name}({code}) 法說會"
        rows.append([
            "法說會", "台股", event_name, date_str, date_str,
            f"{name}（{code}）舉辦法人說明會",
            "https://mops.twse.com.tw/mops/#/web/t100sb07_1", "",
        ])
    # 同一公司同一天只取一筆
    seen = set()
    deduped = []
    for r in rows:
        key = (r[2], r[3])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped


def fetch_tw_legal_meetings(start: datetime, end: datetime) -> list[list]:
    """從 MOPS 抓取未來 30 天的台股法說會（focus watchlist）。

    流程：POST 新版 MOPS API 取得加密 URL → GET 該 URL 取得 HTML → 解析。
    對 focus watchlist 中每家公司逐一查詢。
    """
    tw_watchlist = _load_tw_watchlist(WATCHLIST_FOCUS_CSV)
    if not tw_watchlist:
        print(f"        Warning: {WATCHLIST_FOCUS_CSV} empty or not found.")
        return []

    results = []
    session = requests.Session()
    session.verify = False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "Origin": "https://mops.twse.com.tw",
        "Referer": "https://mops.twse.com.tw/mops/",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }
    try:
        session.get("https://mops.twse.com.tw/mops/", headers=headers, timeout=15)
    except Exception:
        pass

    for symbol, name in tw_watchlist.items():
        code = symbol.replace(".TW", "").replace(".TWO", "")
        try:
            resp = session.post(
                MOPS_REDIRECT_URL,
                json={
                    "apiName": "ajax_t100sb07_1",
                    "parameters": {
                        "co_id": code,
                        "encodeURIComponent": 1,
                        "step": 1,
                        "firstin": 1,
                        "off": 1,
                        "TYPEK": "all",
                    },
                },
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            url = resp.json()["result"]["url"]

            resp2 = session.get(url, timeout=20)
            resp2.raise_for_status()
            found = _parse_mops_company_html(resp2.text, code, name, start, end)
            if found:
                print(f"        {code} {name}: {len(found)} 法說會")
            results.extend(found)
        except Exception as e:
            print(f"  MOPS {code} {name} 抓取失敗: {e}")

    return results


# ── US Earnings (yfinance) ───────────────────────────────────────────────────

def _extract_earnings_dates(symbol: str, company: str, market: str,
                             start: datetime, end: datetime) -> list[list]:
    """共用：從 yfinance calendar 抽出落在範圍內的財報日期。"""
    rows = []
    ticker = yf.Ticker(symbol)
    cal = ticker.calendar
    if cal is None:
        return rows

    dates = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
    if not isinstance(dates, list):
        dates = [dates]

    for dt in dates:
        if dt is None:
            continue
        if hasattr(dt, "to_pydatetime"):
            dt = dt.to_pydatetime()
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if not isinstance(dt, datetime):
            dt = datetime(dt.year, dt.month, dt.day)
        else:
            try:
                dt = dt.replace(tzinfo=None)
            except TypeError:
                dt = datetime(dt.year, dt.month, dt.day)
        dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)

        if start <= dt <= end:
            date_str = dt.strftime("%Y-%m-%d")
            display = symbol.replace(".TW", "").replace(".TWO", "")
            rows.append([
                "財報公告", market,
                f"{company}({display}) 財報",
                date_str, date_str,
                f"{company} 發布季度財報",
                f"https://finance.yahoo.com/quote/{symbol}/financials/",
                f"https://finance.yahoo.com/calendar/earnings?symbol={symbol}",
            ])
    return rows


def fetch_us_earnings(start: datetime, end: datetime) -> list[list]:
    """使用 yfinance 抓取美股財報日期（未來 30 天）。"""
    results = []
    for symbol, company in US_WATCHLIST.items():
        try:
            results.extend(_extract_earnings_dates(symbol, company, "美股", start, end))
        except Exception as e:
            print(f"  {symbol} 財報日期抓取失敗: {e}")
    return results


def _extract_earnings_dates_quiet(symbol: str, company: str, market: str,
                                   start: datetime, end: datetime) -> list[list]:
    """Same as _extract_earnings_dates but suppresses yfinance's 404 stderr noise."""
    buf = io.StringIO()
    old_stderr, old_stdout = sys.stderr, sys.stdout
    sys.stderr = sys.stdout = buf
    try:
        return _extract_earnings_dates(symbol, company, market, start, end)
    except Exception:
        return []
    finally:
        sys.stderr, sys.stdout = old_stderr, old_stdout


def fetch_tw_earnings(start: datetime, end: datetime) -> list[list]:
    """使用 yfinance 抓取台股財報日期（未來 30 天），從 watchlist CSV 載入。
    自動 fallback .TW → .TWO（TPEX 上櫃股需用 .TWO）。
    """
    tw_watchlist = _load_tw_watchlist(WATCHLIST_CSV)
    print(f"        Loaded {len(tw_watchlist)} stocks from {WATCHLIST_CSV}")
    results = []
    tpex_fallbacks = 0
    for symbol, company in tw_watchlist.items():
        # Try .TW first (suppress noisy 404 warnings)
        rows = _extract_earnings_dates_quiet(symbol, company, "台股", start, end)
        # If empty, retry with .TWO (TPEX/OTC stocks use .TWO on Yahoo Finance)
        if not rows and symbol.endswith(".TW"):
            alt = symbol[:-3] + ".TWO"
            try:
                rows = _extract_earnings_dates(alt, company, "台股", start, end)
                if rows:
                    tpex_fallbacks += 1
            except Exception as e:
                print(f"  {symbol} / {alt} 財報日期抓取失敗: {e}")
        results.extend(rows)
    if tpex_fallbacks:
        print(f"        ({tpex_fallbacks} stocks resolved via .TWO fallback)")
    return results


# ── CSV helpers ──────────────────────────────────────────────────────────────

def save_csv(rows: list[list], output_file: str) -> None:
    """Merge new rows into the CSV, deduplicate, sort by date descending, rewrite."""
    # 1. 讀取現有資料
    existing_rows: list[list] = []
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue  # skip header
                    if len(row) >= 4:
                        existing_rows.append(row)
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    # 2. 合併，以 (事件名稱, 開始日期) 去重
    seen: set = set()
    merged: list[list] = []
    for row in existing_rows:
        key = (row[2].strip(), row[3].strip())
        if key not in seen:
            seen.add(key)
            merged.append(row)

    added = 0
    for row in rows:
        if len(row) >= 4:
            key = (row[2].strip(), row[3].strip())
            if key not in seen:
                seen.add(key)
                merged.append(row)
                added += 1

    # 3. 日期降冪排序（新 → 舊）
    merged.sort(key=lambda r: r[3], reverse=True)

    # 4. 整檔重寫
    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(merged)

    total = len(merged)
    if added:
        print(f"Added {added} new events → CSV now has {total} rows.")
    else:
        print(f"No new events. CSV unchanged at {total} rows.")


# ── main ─────────────────────────────────────────────────────────────────────

def generate_upcoming_earnings() -> None:
    start, end = _date_range_30()
    print(f"Fetching upcoming earnings/法說會 events ({start.date()} ~ {end.date()})...")

    all_rows: list[list] = []

    print("  [1/3] Fetching Taiwan 法說會 from MOPS...")
    tw_rows = fetch_tw_legal_meetings(start, end)
    print(f"        Found {len(tw_rows)} Taiwan 法說會 events.")
    all_rows.extend(tw_rows)

    print("  [2/3] Fetching US earnings from yfinance...")
    us_rows = fetch_us_earnings(start, end)
    print(f"        Found {len(us_rows)} US earnings events.")
    all_rows.extend(us_rows)

    print("  [3/3] Fetching Taiwan earnings from yfinance...")
    tw_earn_rows = fetch_tw_earnings(start, end)
    print(f"        Found {len(tw_earn_rows)} Taiwan earnings events.")
    all_rows.extend(tw_earn_rows)

    save_csv(all_rows, OUTPUT_FILE)

    if all_rows:
        print("-" * 50)
        for row in all_rows[:5]:
            print(f"  {row[3]}  {row[0]}/{row[1]}  {row[2]}")
        if len(all_rows) > 5:
            print(f"  ... and {len(all_rows) - 5} more")
        print("-" * 50)


if __name__ == "__main__":
    generate_upcoming_earnings()
