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

OUTPUT_FILE = "raw_event_upcoming_earnings.csv"
CSV_HEADERS = [
    "類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2",
    "download_timestamp", "process_timestamp"
]

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


def _load_us_next_fiscal_quarter() -> dict[str, str]:
    """從 raw_conceptstock_company_metadata.csv 的「即將發布」欄位載入
    {Ticker: 'FY2026 Q4'} -- 每家公司自己的真實財年季度命名（與 SEC 申報一致）。

    _quarter_label() 只能從財報公告日期用固定的「約一季前」位移公式反推涵蓋
    季度，對回報時滯較短的公司（例如 DELL/NVDA，財季結束後約 3-4 週即公告，
    短於公式假設的最長 3 個月）會推算錯一整季。metadata 的「即將發布」是
    ConceptStocks 用公司實際 SEC 申報維護的權威值，可直接使用、不必用日期猜。
    """
    for path in _METADATA_CSV_PATHS:
        if not os.path.exists(path):
            continue
        result = {}
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                ticker = row.get("Ticker", "").strip()
                next_fq = row.get("即將發布", "").strip()
                if ticker and ticker != "-" and next_fq and next_fq != "-":
                    result[ticker] = next_fq
        return result
    return {}

US_WATCHLIST = _load_us_watchlist()
US_NEXT_FISCAL_QUARTER = _load_us_next_fiscal_quarter()

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

_QUARTER_RE = re.compile(r'\d{4}\s+Q[1-4]')
_FISCAL_QUARTER_RE = re.compile(r'FY\d{4}\s+Q[1-4]')
_TICKER_RE = re.compile(r'\(([^()]+)\)')


def _quarter_label(event_date: datetime) -> str:
    """從事件日期推算季度標籤，例如 '2026 Q1'。
    法說會慣例：
      1–3 月 → 前一年 Q4
      4–6 月 → 當年 Q1
      7–9 月 → 當年 Q2
      10–12 月 → 當年 Q3
    """
    m = event_date.month
    if m <= 3:
        return f"{event_date.year - 1} Q4"
    elif m <= 6:
        return f"{event_date.year} Q1"
    elif m <= 9:
        return f"{event_date.year} Q2"
    else:
        return f"{event_date.year} Q3"


def _normalize_fashuohui_name(event_name: str, date_str: str, category: str) -> str:
    """確保法說會事件名稱包含季度，例如 '台積電(2330) 2026 Q1 法說會'。
    若已含 'YYYY Qn' 則直接回傳；否則根據日期插入季度。
    """
    if category != "法說會":
        return event_name
    if _QUARTER_RE.search(event_name):
        return event_name  # 已包含季度，不重複加
    suffix = " 法說會"
    if not event_name.endswith(suffix):
        return event_name
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        quarter = _quarter_label(event_date)
        base = event_name[: -len(suffix)]
        return f"{base} {quarter} 法說會"
    except Exception:
        return event_name


def _normalize_earnings_name(event_name: str, date_str: str, category: str) -> str:
    """確保財報公告事件名稱包含季度，例如 'Apple Inc.(AAPL) 2026 Q1 財報'。
    若已含 'YYYY Qn' 則直接回傳；否則根據日期插入季度。
    季度推算規則（與法說會相同）：
      1–3 月 → 前一年 Q4、4–6 月 → 當年 Q1、7–9 月 → 當年 Q2、10–12 月 → 當年 Q3
    """
    if category != "財報公告":
        return event_name
    if _QUARTER_RE.search(event_name):
        return event_name  # 已包含季度，不重複加
    suffix = " 財報"
    if not event_name.endswith(suffix):
        return event_name
    try:
        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        quarter = _quarter_label(event_date)
        base = event_name[: -len(suffix)]
        return f"{base} {quarter} 財報"
    except Exception:
        return event_name


def _extract_event_ticker(event_name: str) -> str | None:
    """Return the ticker/code from the final parenthesized token in an event name."""
    matches = _TICKER_RE.findall(event_name)
    if not matches:
        return None
    ticker = matches[-1].strip()
    return ticker or None


def _is_fiscal_quarter_name(event_name: str) -> bool:
    return bool(_FISCAL_QUARTER_RE.search(event_name))


def _earnings_row_score(row: list) -> tuple[int, int, int, int]:
    """Higher score wins when duplicate earnings rows describe the same event."""
    name = row[2] if len(row) > 2 else ""
    ticker = _extract_event_ticker(name)
    preferred_company = US_WATCHLIST.get(ticker, "") if ticker else ""
    has_preferred_company = int(bool(preferred_company and name.startswith(f"{preferred_company}(")))
    return (
        int(_is_fiscal_quarter_name(name)),
        has_preferred_company,
        len(row[5]) if len(row) > 5 else 0,
        len(name),
    )


def _merge_earnings_duplicate_rows(preferred: list, duplicate: list) -> list:
    """Merge two same-company earnings rows, keeping the better label and a full date range."""
    if _earnings_row_score(duplicate) > _earnings_row_score(preferred):
        preferred, duplicate = duplicate, preferred

    dates = [d for d in [preferred[3], preferred[4], duplicate[3], duplicate[4]] if d]
    if dates:
        preferred[3] = min(dates)
        preferred[4] = max(dates)

    return preferred


def _dedupe_nearby_earnings_events(rows: list[list]) -> list[list]:
    """Collapse duplicate 財報公告 rows for the same ticker on the same/next day.

    yfinance may emit a calendar-quarter event while an existing/manual row already has
    the correct fiscal-quarter label. Treat same ticker + market + category within one
    day as the same earnings event and keep the more specific row.
    """
    grouped: dict[tuple[str, str, str], list[list]] = {}
    passthrough: list[list] = []

    for row in rows:
        if len(row) < 4 or row[0] != "財報公告":
            passthrough.append(row)
            continue
        ticker = _extract_event_ticker(row[2])
        if not ticker:
            passthrough.append(row)
            continue
        grouped.setdefault((row[0], row[1], ticker), []).append(row)

    deduped = passthrough[:]
    removed = 0

    for group_rows in grouped.values():
        parsed: list[tuple[datetime, list]] = []
        unparsed: list[list] = []
        for row in group_rows:
            try:
                parsed.append((datetime.strptime(row[3], "%Y-%m-%d"), row))
            except Exception:
                unparsed.append(row)

        parsed.sort(key=lambda item: item[0])
        clusters: list[list[list]] = []
        for dt, row in parsed:
            if not clusters:
                clusters.append([row])
                continue
            last_date = datetime.strptime(clusters[-1][-1][3], "%Y-%m-%d")
            if abs((dt - last_date).days) <= 1:
                clusters[-1].append(row)
            else:
                clusters.append([row])

        for cluster in clusters:
            merged = cluster[0]
            for row in cluster[1:]:
                merged = _merge_earnings_duplicate_rows(merged, row)
                removed += 1
            deduped.append(merged)
        deduped.extend(unparsed)

    if removed:
        print(f"  [DEDUP] 合併 {removed} 筆同 ticker、日期相近的財報重複事件")

    return deduped


def _date_range_30() -> tuple[datetime, datetime]:
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=30), today + timedelta(days=60)


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
        quarter = _quarter_label(event_date)
        event_name = f"{name}({code}) {quarter} 法說會"
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
            # Prefer the company's own real fiscal-quarter label (ConceptStocks
            # metadata, sourced from actual SEC filings) over the date-shift
            # heuristic, which assumes a roughly one-quarter reporting lag and
            # mislabels companies that report sooner after quarter-end (e.g.
            # DELL/NVDA report ~3-4 weeks post quarter-end, not up to 3 months).
            quarter = US_NEXT_FISCAL_QUARTER.get(symbol) or _quarter_label(dt)
            rows.append([
                "財報公告", market,
                f"{company}({display}) {quarter} 財報",
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
            rows = _extract_earnings_dates_quiet(alt, company, "台股", start, end)
            if rows:
                tpex_fallbacks += 1
        results.extend(rows)
    if tpex_fallbacks:
        print(f"        ({tpex_fallbacks} stocks resolved via .TWO fallback)")
    return results


# ── CSV helpers ──────────────────────────────────────────────────────────────

def _sync_tw_earnings_dates_from_mops(all_rows: list[list]) -> list[list]:
    """Post-processing: for Taiwan 財報公告, if a matching MOPS 法說會 date exists
    for the same company+quarter and the MOPS date is earlier, use MOPS date.

    Background: yfinance often returns inaccurate estimated dates for Taiwan stocks.
    The MOPS 法說會 date reflects the actual board meeting date (董事會), which is
    also when the financial report is officially released — making it more reliable.
    """
    code_quarter_re = re.compile(r'\((\d{4,5})\)\s+(\d{4}\s+Q[1-4])')

    # Build map {(stock_code, quarter): earliest_mops_date} from 法說會 entries
    mops_dates: dict[tuple, str] = {}
    for row in all_rows:
        if row[0] == "法說會" and row[1] == "台股":
            m = code_quarter_re.search(row[2])
            if m:
                key = (m.group(1), m.group(2))
                existing = mops_dates.get(key)
                if existing is None or row[3] < existing:
                    mops_dates[key] = row[3]

    if not mops_dates:
        return all_rows

    updated = 0
    for row in all_rows:
        if row[0] == "財報公告" and row[1] == "台股":
            m = code_quarter_re.search(row[2])
            if m:
                key = (m.group(1), m.group(2))
                mops_date = mops_dates.get(key)
                if mops_date and mops_date < row[3]:
                    print(f"  [DATE SYNC] {row[2]}: {row[3]} → {mops_date} (從 MOPS 法說會修正)")
                    row[3] = mops_date
                    row[4] = mops_date
                    updated += 1

    if updated:
        print(f"  [DATE SYNC] 共修正 {updated} 筆台股財報日期（MOPS 法說會資料）")

    return all_rows


def save_csv(rows: list[list], output_file: str) -> None:
    """Merge new rows into the CSV, deduplicate by event name, sort by date descending, rewrite.

    Deduplication key is event_name only (not event_name + date), so that corrected dates
    from the current fetch can override stale dates stored in the existing CSV.
    New rows take precedence over existing rows for the same event name.
    """
    process_timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 讀取現有資料，以事件名稱為 key 建立 lookup
    existing_by_name: dict[str, list] = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue  # skip header
                    if len(row) >= 4:
                        row[2] = _normalize_fashuohui_name(row[2], row[3], row[0])
                        row[2] = _normalize_earnings_name(row[2], row[3], row[0])
                        while len(row) < len(CSV_HEADERS):
                            row.append(process_timestamp)
                        row[-2] = process_timestamp
                        row[-1] = process_timestamp
                        name = row[2].strip()
                        if name not in existing_by_name:
                            existing_by_name[name] = row
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    # 2. 新資料覆蓋同名既有資料（允許日期更新），否則新增
    added = updated_dates = 0
    for row in rows:
        if len(row) < 4:
            continue
        row[2] = _normalize_fashuohui_name(row[2], row[3], row[0])
        row[2] = _normalize_earnings_name(row[2], row[3], row[0])
        name = row[2].strip()
        while len(row) < len(CSV_HEADERS):
            row.append(process_timestamp)
        row[-2] = process_timestamp
        row[-1] = process_timestamp
        if name in existing_by_name:
            old_date = existing_by_name[name][3]
            if old_date != row[3].strip():
                print(f"  [DATE UPDATE] {name}: {old_date} → {row[3].strip()}")
                existing_by_name[name][3] = row[3].strip()
                existing_by_name[name][4] = row[4].strip()
                updated_dates += 1
        else:
            existing_by_name[name] = row
            added += 1

    merged = list(existing_by_name.values())
    merged = _dedupe_nearby_earnings_events(merged)

    # 3. 日期降冪排序（新 → 舊）
    merged.sort(key=lambda r: r[3], reverse=True)

    # 4. 整檔重寫
    with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        writer.writerows(merged)

    total = len(merged)
    parts = []
    if added:
        parts.append(f"新增 {added} 筆")
    if updated_dates:
        parts.append(f"更新日期 {updated_dates} 筆")
    if parts:
        print(f"{' / '.join(parts)} → CSV 共 {total} 筆。")
    else:
        print(f"無變更。CSV 共 {total} 筆。")


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

    print("  [4/4] Syncing Taiwan 財報 dates from MOPS 法說會 data...")
    all_rows = _sync_tw_earnings_dates_from_mops(all_rows)

    save_csv(all_rows, OUTPUT_FILE)

    if all_rows:
        print("-" * 50)
        for row in all_rows[:5]:
            print(f"  {row[3]}  {row[0]}/{row[1]}  {row[2]}")
        if len(all_rows) > 5:
            print(f"  ... and {len(all_rows) - 5} more")
        print("-" * 50)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (default: today-30d)")
    parser.add_argument("--end",   type=str, help="End date YYYY-MM-DD (default: today+60d)")
    args = parser.parse_args()

    if args.start or args.end:
        _start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else _date_range_30()[0]
        _end   = datetime.strptime(args.end,   "%Y-%m-%d") if args.end   else _date_range_30()[1]
        # Temporarily override _date_range_30 for generate_upcoming_earnings
        _orig = _date_range_30
        def _date_range_30(): return _start, _end  # noqa: E306
        generate_upcoming_earnings()
        _date_range_30 = _orig
    else:
        generate_upcoming_earnings()
