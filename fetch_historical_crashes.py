import os
import csv
import io
from dotenv import load_dotenv
from llm import LLMClient

load_dotenv()

OUTPUT_FILE = "historical_crashes.csv"
CSV_HEADERS = ["類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"]

PROMPT = """
You are a financial historian.

Task: Search for and extract a list of the TOP 100 CRITICAL historical events from 1990 to the present that caused significant stock market drops (crashes, corrections, or bear markets) in either the Global (US) or Taiwan markets.

Focus on these specific Categories (類別) and Sub-categories (子類別):

1. 金融危機 (Financial Crisis):
   - 亞洲金融風暴 (Asian Financial Crisis)
   - 網路泡沫 (Dot-com Bubble)
   - 次貸危機 (Subprime Crisis / Global Financial Crisis)
   - 歐債危機 (European Debt Crisis)
   - 銀行倒閉 (Bank Failure)

2. 公共衛生 (Public Health):
   - 傳染病爆發 (Pandemic) - e.g., SARS, COVID-19

3. 地緣政治 (Geopolitics):
   - 恐怖攻擊 (Terrorist Attack) - e.g., 911
   - 戰爭衝突 (War & Conflict) - e.g., Persian Gulf War, Russia-Ukraine
   - 貿易戰 (Trade War)
   - 政治黑天鵝 (Political Black Swan) - e.g., Brexit, 1996 Taiwan Strait Crisis (台海飛彈危機)

4. 自然災害 (Natural Disaster):
   - 重大震災 (Major Earthquake) - e.g., 921 Earthquake, 311 Japan Earthquake

5. 政策衝擊 (Policy Shock):
   - 貨幣政策 (Monetary Policy) - e.g., Aggressive Rate Hikes
   - 證所稅事件 (Stock Transaction Tax) - Specific to Taiwan (1990)

Output Format:
Produce a valid CSV file content with the following headers:
"類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"

Requirements:
- Language: All text must be in Traditional Chinese (繁體中文).
- Dates: Format YYYY-MM-DD.
- "備註" (Note): Briefly explain the impact (e.g., "跌幅達...").
- "Link1": MANDATORY. Provide a reliable source URL.
- Quantity & Distribution: Find roughly 40 events in total, distributed as follows:
    * 1990-1999: ~10 events
    * 2000-2009: ~10 events
    * 2010-2019: ~10 events
    * 2020-Present: ~10 events
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
    new_rows = []
    header = None
    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)
        if rows:
            header = rows[0]
            new_rows = rows[1:]
    except csv.Error as e:
        print(f"Error parsing CSV response: {e}")
        return

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
            print(f"Warning: Could not read existing file for deduplication: {e}")

    rows_to_write = []
    for row in new_rows:
        if len(row) >= 4:
            key = (row[2].strip(), row[3].strip())
            if key not in existing_keys:
                rows_to_write.append(row)
                existing_keys.add(key)

    if rows_to_write:
        mode = "a" if os.path.exists(output_file) else "w"
        with open(output_file, mode, encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if write_header and header:
                writer.writerow(header)
            writer.writerows(rows_to_write)
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
