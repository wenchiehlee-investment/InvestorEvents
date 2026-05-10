import os
import csv
import io
from datetime import date, timedelta
from dotenv import load_dotenv
from llm import LLMClient

load_dotenv()

OUTPUT_FILE = "raw_event_jesen.huang_talk.csv"
CSV_HEADERS = ["類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"]


def build_prompt() -> str:
    today = date.today()
    window_start = (today - timedelta(weeks=2)).isoformat()
    window_end = (today + timedelta(weeks=2)).isoformat()
    return f"""
You are a Technology Industry Analyst tracking NVIDIA CEO Jensen Huang's public appearances.

Today's date: {today.isoformat()}
Target window: {window_start} to {window_end} (2 weeks before and 2 weeks after today)

Task: Search for Jensen Huang's confirmed or scheduled talks, speeches, keynotes, interviews, panels, and public appearances within this window. Include recent past events AND upcoming events.

Focus on:
1. Keynote speeches at major tech/AI conferences (e.g., GTC, Computex, CES, Hot Chips, SC, AWS re:Invent).
2. Investor/earnings call appearances or analyst day presentations.
3. High-profile media interviews (Bloomberg, CNBC, WSJ, Financial Times).
4. University commencement addresses or special lectures.
5. Government or policy forums (e.g., Senate hearings, White House meetings).
6. Product launch or partnership announcements where Jensen Huang speaks.

For each event, categorize using these 類別/子類別:
- 主題演講 / 科技大會 (Keynote / Tech Conference)
- 主題演講 / 產品發布 (Keynote / Product Launch)
- 投資人活動 / 法說會 (Investor / Earnings Call)
- 投資人活動 / 分析師日 (Investor / Analyst Day)
- 媒體訪談 / 電視採訪 (Media / TV Interview)
- 媒體訪談 / 播客訪談 (Media / Podcast)
- 政策論壇 / 國會聽證 (Policy / Congressional Hearing)
- 政策論壇 / 政府會議 (Policy / Government Meeting)
- 學術活動 / 大學演講 (Academic / University Speech)

Output Format:
Produce a valid CSV file content with the following headers (no quotes):
類別,子類別,事件名稱,開始日期,結束日期,備註,Link1,Link2

Requirements:
- Language: All text must be in Traditional Chinese (繁體中文), except proper nouns (event names, organizations) which may keep English.
- Dates: Format YYYY-MM-DD. If only a single day, repeat the same date for 開始日期 and 結束日期.
- "事件名稱": Include the event/conference name and Jensen Huang's role (e.g., "Jensen Huang 於 GTC 2026 發表主題演講").
- "備註": Describe the key topics discussed or announced, and any market/stock impact if applicable.
- "Link1": MANDATORY. Provide a reliable source URL (NVIDIA IR, Reuters, Bloomberg, CNBC, official conference site).
- Only include events in the window {window_start} to {window_end}.
- Do not include markdown code block markers.
- Aim for ALL events in the window, not just top ones.
"""


def clean_csv(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _clean_cell(v: str) -> str:
    v = v.strip()
    if v.startswith('"') and v.endswith('"'):
        v = v[1:-1].strip()
    return v


def save_csv(csv_content: str, output_file: str) -> None:
    new_rows = []
    header = None
    try:
        reader = csv.reader(io.StringIO(csv_content))
        rows = [[_clean_cell(c) for c in row] for row in reader]
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

    if not os.path.exists(output_file):
        write_header = True

    if rows_to_write or write_header:
        mode = "w" if write_header else "a"
        with open(output_file, mode, encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if write_header and header:
                writer.writerow(header)
            writer.writerows(rows_to_write)
        if rows_to_write:
            print(f"Appended {len(rows_to_write)} new events to '{output_file}'.")
        else:
            print(f"No new unique events to append to '{output_file}'.")
    else:
        print(f"No new unique events to append to '{output_file}'.")


def generate_jensen_huang_talk_events() -> None:
    today = date.today()
    window_start = (today - timedelta(weeks=2)).isoformat()
    window_end = (today + timedelta(weeks=2)).isoformat()
    print(f"Fetching Jensen Huang talk/speech events ({window_start} to {window_end})...")
    print("Sending request to LLM...")

    try:
        client = LLMClient(app_name="InvestorEvents")
        prompt = build_prompt()
        csv_content = clean_csv(client.generate_smart("InvestorEvents_FetchJesenHuangTalkEvents", prompt, draft_provider="codex"))
        save_csv(csv_content, OUTPUT_FILE)

        print("-" * 50)
        print(csv_content[:800].encode("utf-8", errors="replace").decode("utf-8") + "\n...(truncated)")
        print("-" * 50)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    generate_jensen_huang_talk_events()
