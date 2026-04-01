# Raw CSV Column Definitions - InvestorEvents
## Events and Earnings Calendar Data

### Version History:
- **v1.0.0** (2026-04-01): Initial column definition for upcoming earnings events.

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

### File Characteristics:
- **Standalone file**: Does not include standard GoodInfo metadata columns.
- **Sync Destination**: Synchronized to `InvestorConference` for portal display.
- **Update Frequency**: Weekly or on-demand via `weekly-earnings.yml`.
