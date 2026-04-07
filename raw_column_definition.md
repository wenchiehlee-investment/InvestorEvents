---
source: https://raw.githubusercontent.com/wenchiehlee-investment/InvestorEvents/refs/heads/main/raw_column_definition.md
destination: https://raw.githubusercontent.com/wenchiehlee-investment/Python-Actions.GoodInfo.Analyzer/refs/heads/main/definitions/raw_column_definition_InvestorEvents.md
---

# Raw CSV Column Definitions - InvestorEvents
## Events and Earnings Calendar Data

---

## raw_event_upcoming_earnings.csv (Upcoming Earnings Calendar)
**No:** 60
**Source:** `fetch_upcoming_earnings.py` via Yahoo Finance / News
**Extraction Strategy:** Aggregates upcoming earnings release dates for both Taiwan and US stocks.

### Column Definitions:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `類別` | string | Event category | `財報公告` |
| `子類別` | string | Sub-category (market or region) | `美股`, `台股` |
| `事件名稱` | string | Full description of the event | `台積電(2330) 財報` |
| `開始日期` | date | Event start date (YYYY-MM-DD) | `2026-04-16` |
| `結束日期` | date | Event end date (YYYY-MM-DD) | `2026-04-16` |
| `備註` | string | Additional details | `台積電 發布季度財報` |
| `Link1` | url | Primary reference link (e.g., Yahoo Financials) | `https://finance.yahoo.com/quote/2330.TW/financials/` |
| `Link2` | url | Secondary reference link (e.g., Yahoo Earnings Calendar) | `https://finance.yahoo.com/calendar/earnings?symbol=2330.TW` |

---

## raw_event_historical_crashes.csv (Historical Market Crashes)
**No:** 61
**Source:** `fetch_historical_crashes.py` via LLM / Financial News
**Extraction Strategy:** Uses LLM to identify and describe significant market corrections and crashes from 2020 to 2026.

### Column Definitions:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `類別` | string | Event category | `金融危機`, `地緣政治` |
| `子類別` | string | Detailed event type | `日圓套利交易平倉`, `戰爭衝突` |
| `事件名稱` | string | Event name | `Black Monday / Yen Carry Trade Unwind` |
| `開始日期` | date | Crash start date (YYYY-MM-DD) | `2024-08-05` |
| `結束日期` | date | Crash end date (YYYY-MM-DD) | `2024-08-05` |
| `備註` | string | Impact description | `日圓套利交易平倉引發全球崩盤...` |

---

## raw_event_ai_events.csv (AI Technology & Market Events)
**No:** 62
**Source:** `fetch_ai_events.py` via LLM / Financial News

### Column Definitions:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `類別` | string | Event category | `市場與資本`, `產品發布` |
| `子類別` | string | Detailed event type | `市值里程碑`, `生成式AI應用` |
| `事件名稱` | string | Event name | `ChatGPT Launch` |
| `開始日期` | date | Event start date (YYYY-MM-DD) | `2022-11-30` |
| `結束日期` | date | Event end date (YYYY-MM-DD) | `2022-11-30` |
| `備註` | string | Business/Market impact | `引發全球 AI 軍備競賽...` |

---

## raw_event_nvidia_events.csv (NVIDIA Product & Business Milestones)
**No:** 63
**Source:** `fetch_nvidia_events.py` via LLM / Financial News

### Column Definitions:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `類別` | string | Event category | `硬體發布`, `財務里程碑` |
| `子類別` | string | Detailed event type | `GPU 產品`, `營收突破` |
| `事件名稱` | string | Event name | `H100 Announcement` |
| `開始日期` | date | Event date (YYYY-MM-DD) | `2022-03-22` |
| `結束日期` | date | Event date (YYYY-MM-DD) | `2022-03-22` |
| `備註` | string | Business impact | `NVIDIA Hopper 架構發布，奠定 AI 算力基礎...` |

---

## raw_event_stock_events.csv (Critical Stock Market Events)
**No:** 64
**Source:** `fetch_stock_events.py` via LLM / Financial News

### Column Definitions:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `類別` | string | Event category | `市場結構`, `產業趨勢` |
| `子類別` | string | Detailed event type | `泡沫爆破`, `科技板塊` |
| `事件名稱` | string | Event name | `Dot-com Bubble Burst` |
| `開始日期` | date | Event date (YYYY-MM-DD) | `2000-03-10` |
| `結束日期` | date | Event date (YYYY-MM-DD) | `2002-10-09` |
| `備註` | string | Business impact | `網際網路泡沫破裂，導致納斯達克指數重挫...` |
