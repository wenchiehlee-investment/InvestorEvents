import os
import csv
import io
from datetime import datetime
from dotenv import load_dotenv
from llm import LLMClient

load_dotenv()

OUTPUT_FILE = "raw_event_historical_crashes.csv"
CSV_HEADERS = [
    "類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2",
    "download_timestamp", "process_timestamp"
]

PROMPT = """
You are a financial historian specializing in modern market volatility.

Task: Search for and extract a list of CRITICAL events from 2020-01-01 to 2026-04-01 that caused significant stock market drops (crashes, corrections, or bear markets) in either the Global (US) or Taiwan markets.

Special Focus (2024-2026):
- 2024-08-05: Black Monday / Yen Carry Trade Unwind (日圓套利交易平倉引發全球崩盤)
- 2024-04-19: Israel-Iran Conflict Escalation (以色列-伊朗衝突升級導致台股創紀錄大跌)
- 2024-01-01: Noto Peninsula Earthquake (能登半島地震)
- 2024-04-03: Hualien Earthquake (0403 花蓮大地震)
- 2024-10-01: Middle East War Expansion (中東戰火擴大)
- 2025-01-20: New US Administration Policy Shocks (新任美國政府政策衝擊/關稅政策)

Focus on these specific Categories (類別) and Sub-categories (子類別):

1. 金融危機 (Financial Crisis):
   - 銀行倒閉 (Bank Failure) - e.g., Silicon Valley Bank (2023)
   - 日圓套利交易平倉 (Yen Carry Trade Unwind - 2024)

2. 公共衛生 (Public Health):
   - 傳染病爆發 (Pandemic) - COVID-19 (2020-2022)

3. 地緣政治 (Geopolitics):
   - 戰爭衝突 (War & Conflict) - Russia-Ukraine (2022), Israel-Hamas (2023-2024)
   - 貿易戰/制裁 (Trade War & Sanctions) - US-China AI Chip Bans (2024)

4. 自然災害 (Natural Disaster):
   - 重大事件 (Major Events) - e.g., Hualien Earthquake (2024)

5. 政策衝擊 (Policy Shock):
   - 貨幣政策 (Monetary Policy) - Aggressive Fed Rate Hikes (2022-2023), BOJ Rate Hike (2024)

Output Format:
Produce a valid CSV file content with the following headers:
"類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"

Requirements:
- Language: All text must be in Traditional Chinese (繁體中文).
- Dates: Format YYYY-MM-DD.
- "備註" (Note): Briefly explain the impact (e.g., "台股單日重挫...").
- "Link1": MANDATORY. Provide a reliable source URL.
- Quantity: Find about 20 high-quality events from 2020 to 2026.
- Do not include markdown code block markers.
"""


def clean_csv(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def save_csv(csv_content: str, output_file: str) -> None:
    process_timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    new_rows = []
    header = None
    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        if rows:
            header = list(CSV_HEADERS)
            new_rows = rows[1:]
    except csv.Error as e:
        print(f"Error parsing CSV response: {e}")
        return

    existing_keys: set = set()
    existing_rows = []

    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if i == 0:
                        continue
                    if len(row) >= 4:
                        while len(row) < len(CSV_HEADERS):
                            row.append(process_timestamp)
                        row[-2] = process_timestamp
                        row[-1] = process_timestamp
                        existing_rows.append(row)
                        existing_keys.add((row[2].strip(), row[3].strip()))
        except Exception as e:
            print(f"Warning: Could not read existing file for deduplication: {e}")

    rows_to_write = []
    for row in new_rows:
        if len(row) >= 4:
            key = (row[2].strip(), row[3].strip())
            if key not in existing_keys:
                while len(row) < len(CSV_HEADERS):
                    row.append(process_timestamp)
                row[-2] = process_timestamp
                row[-1] = process_timestamp
                rows_to_write.append(row)
                existing_keys.add(key)

    if rows_to_write or existing_rows:
        with open(output_file, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header or CSV_HEADERS)
            writer.writerows(existing_rows + rows_to_write)
    if rows_to_write:
        print(f"Appended {len(rows_to_write)} new events to '{output_file}'.")
    else:
        print(f"No new unique events to append to '{output_file}'.")


def generate_historical_crashes() -> None:
    print("Fetching historical market crash events (1990-Present)...")
    print("Sending request to Codex (chatgpt-pro)...")

    try:
        client = LLMClient(app_name="InvestorEvents")
        csv_content = clean_csv(client.generate(PROMPT))
        save_csv(csv_content, OUTPUT_FILE)

        print("-" * 50)
        print(csv_content[:800] + "\n...(truncated)")
        print("-" * 50)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    generate_historical_crashes()
