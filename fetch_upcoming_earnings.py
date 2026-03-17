"""Fetch upcoming 30-day earnings reports (財報) and investor conferences (法說會)
for TWSE/TPEX (Taiwan) and major US stocks.

Data sources:
- Taiwan 法說會: MOPS (公開資訊觀測站)
- US Earnings:   yfinance
"""

import csv
import os
import re
from datetime import datetime, timedelta

import httpx
import requests
import urllib3
import yfinance as yf
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

OUTPUT_FILE = "upcoming_earnings.csv"
CSV_HEADERS = ["類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"]

# 監控的美股清單（主要 AI / 科技 / 半導體）
US_WATCHLIST = {
    "NVDA":  "NVIDIA",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet(Google)",
    "AAPL":  "Apple",
    "META":  "Meta",
    "AMZN":  "Amazon",
    "TSLA":  "Tesla",
    "AMD":   "AMD",
    "TSM":   "台積電(TSM)",
    "AVGO":  "Broadcom",
    "QCOM":  "Qualcomm",
    "INTC":  "Intel",
    "SMCI":  "Super Micro",
    "ORCL":  "Oracle",
    "CRM":   "Salesforce",
    "ASML":  "ASML",
    "MU":    "Micron",
    "ARM":   "ARM Holdings",
}

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

MOPS_LEGAL_URL = "https://mops.twse.com.tw/mops/web/ajax_t100sb01_1"
MOPS_BASE_URL  = "https://mops.twse.com.tw/mops/web/t100sb01"


def _date_range_30() -> tuple[datetime, datetime]:
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    return today, today + timedelta(days=30)


# ── Taiwan 法說會 (MOPS) ─────────────────────────────────────────────────────

def _roc_ym_pairs(start: datetime, end: datetime) -> list[tuple[int, int]]:
    """Return (ROC year, month) pairs covering the date range."""
    pairs = []
    cur = start.replace(day=1)
    while cur <= end:
        pairs.append((cur.year - 1911, cur.month))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return pairs


def _parse_mops_html(html: str, start: datetime, end: datetime, typek_label: str) -> list[list]:
    """Extract rows from MOPS HTML table."""
    rows = []
    # Match <tr> blocks with td content
    tr_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for tr in tr_blocks:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL | re.IGNORECASE)
        tds = [re.sub(r"<[^>]+>", "", td).strip() for td in tds]
        if len(tds) < 3:
            continue
        # Expected columns: 公司代號, 公司名稱, 日期(民國), 時間, 地點, ...
        code = tds[0].strip()
        name = tds[1].strip()
        date_roc = tds[2].strip()   # e.g. "114/03/25"
        if not re.match(r"\d{3}/\d{2}/\d{2}", date_roc):
            continue
        try:
            y, m, d = date_roc.split("/")
            event_date = datetime(int(y) + 1911, int(m), int(d))
        except ValueError:
            continue
        if not (start <= event_date <= end):
            continue

        date_str = event_date.strftime("%Y-%m-%d")
        event_name = f"{name}({code}) 法說會"
        link1 = MOPS_BASE_URL
        rows.append([
            "法說會", typek_label, event_name, date_str, date_str,
            f"上市公司 {name}（{code}）舉辦法人說明會",
            link1, "",
        ])
    return rows


def fetch_tw_legal_meetings(start: datetime, end: datetime) -> list[list]:
    """從 MOPS 抓取未來 30 天的台股法說會（上市 + 上櫃）。"""
    results = []
    session = requests.Session()
    session.verify = False
    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    }
    # 先 GET 主頁取得 session cookie
    try:
        session.get(MOPS_BASE_URL, headers=browser_headers, timeout=15)
    except Exception:
        pass

    for typek, label in [("sii", "台股上市"), ("otc", "台股上櫃")]:
        for roc_year, month in _roc_ym_pairs(start, end):
            try:
                resp = session.post(
                    MOPS_LEGAL_URL,
                    data={
                        "encodeURIComponent": "1",
                        "step": "2",
                        "firstin": "1",
                        "off": "1",
                        "keyword4": "",
                        "code1": "",
                        "TYPEK": typek,
                        "year": str(roc_year),
                        "month": str(month).zfill(2),
                        "b_date": "",
                        "e_date": "",
                        "isnew": "false",
                    },
                    headers={**browser_headers, "Referer": MOPS_BASE_URL,
                             "Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30,
                )
                resp.raise_for_status()
                results.extend(_parse_mops_html(resp.text, start, end, label))
            except Exception as e:
                print(f"  MOPS {label} {roc_year}/{month:02d} 抓取失敗: {e}")
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


def fetch_tw_earnings(start: datetime, end: datetime) -> list[list]:
    """使用 yfinance 抓取台股財報日期（未來 30 天），從 watchlist CSV 載入。"""
    tw_watchlist = _load_tw_watchlist(WATCHLIST_CSV)
    print(f"        Loaded {len(tw_watchlist)} stocks from {WATCHLIST_CSV}")
    results = []
    for symbol, company in tw_watchlist.items():
        try:
            results.extend(_extract_earnings_dates(symbol, company, "台股", start, end))
        except Exception as e:
            print(f"  {symbol} 財報日期抓取失敗: {e}")
    return results


# ── CSV helpers ──────────────────────────────────────────────────────────────

def save_csv(rows: list[list], output_file: str) -> None:
    existing_keys: set = set()
    write_header = True

    if os.path.exists(output_file):
        write_header = False
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue
                    if len(row) >= 4:
                        existing_keys.add((row[2].strip(), row[3].strip()))
        except Exception as e:
            print(f"Warning: Could not read existing file: {e}")

    rows_to_write = []
    for row in rows:
        if len(row) >= 4:
            key = (row[2].strip(), row[3].strip())
            if key not in existing_keys:
                rows_to_write.append(row)
                existing_keys.add(key)

    if rows_to_write:
        mode = "a" if os.path.exists(output_file) else "w"
        with open(output_file, mode, encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(CSV_HEADERS)
            writer.writerows(rows_to_write)
        print(f"Appended {len(rows_to_write)} new events to '{output_file}'.")
    else:
        print(f"No new unique events to append to '{output_file}'.")


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

    # Sort by date
    all_rows.sort(key=lambda r: r[3])

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
