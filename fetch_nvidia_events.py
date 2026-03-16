import os
import csv
import io
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

OUTPUT_FILE = "nvidia_events.csv"
CSV_HEADERS = ["類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"]

PROMPT = """
You are a Semiconductor Industry Analyst specializing in AI hardware and GPU markets.

Task: Search for and extract a list of the TOP 50-80 CRITICAL NVIDIA AI hardware and business events from 2012 to the present that significantly impacted NVIDIA's stock price, competitive landscape, or the broader AI infrastructure market.

Focus on events that:
1. Launched or announced new GPU/hardware products that shifted the AI compute landscape.
2. Caused significant NVIDIA stock price movements (up or down).
3. Shaped data center, hyperscaler, or cloud GPU adoption trends.
4. Involved regulatory actions (chip export bans) affecting NVIDIA's business.
5. Reflected competitive dynamics (AMD, Intel, custom ASICs from Google/Amazon/Microsoft).

Focus on these specific Categories (類別) and Sub-categories (子類別):

1. 硬體發布 (Hardware Launch):
   - GPU架構 (GPU Architecture) - e.g., Pascal, Volta, Ampere, Hopper, Blackwell architecture announcements.
   - 旗艦產品 (Flagship Product) - e.g., A100, H100, H200, B100, GB200 NVL launch/shipment.
   - 消費級GPU (Consumer GPU) - e.g., GeForce RTX 40/50 series with AI features (DLSS).
   - 網路與系統 (Networking & Systems) - e.g., NVLink, NVSwitch, DGX systems, MGX platforms.

2. 軟體與生態 (Software & Ecosystem):
   - 平台發布 (Platform Launch) - e.g., CUDA milestones, TensorRT, NIM microservices.
   - AI框架整合 (AI Framework Integration) - e.g., cuDNN, support for PyTorch/TensorFlow.

3. 財務與市場 (Financial & Market):
   - 財報里程碑 (Earnings Milestone) - e.g., first $10B quarter, data center revenue surpasses gaming.
   - 市值紀錄 (Market Cap Record) - e.g., NVIDIA becomes most valuable company, exceeds $1T/$2T/$3T.
   - 股票分割 (Stock Split) - e.g., 10:1 stock split in 2024.

4. 政策與競爭 (Policy & Competition):
   - 出口管制 (Export Controls) - e.g., A100/H100 export ban to China, H20 restrictions.
   - 競爭威脅 (Competitive Threat) - e.g., AMD MI300X launch, Google TPU v5, Amazon Trainium.
   - 反壟斷 (Antitrust) - e.g., regulatory scrutiny of NVIDIA's market dominance.

5. 戰略合作 (Strategic Partnerships):
   - 超大規模雲端 (Hyperscaler Deals) - e.g., Microsoft Azure H100 clusters, AWS partnership.
   - 主權AI (Sovereign AI) - e.g., national AI infrastructure deals.

Output Format:
Produce a valid CSV file content with the following headers:
"類別", "子類別", "事件名稱", "開始日期", "結束日期", "備註", "Link1", "Link2"

Requirements:
- Language: All text must be in Traditional Chinese (繁體中文).
- Dates: Format YYYY-MM-DD.
- "備註" (Note): Explain the market/business impact (e.g., "H100需求爆發帶動NVIDIA股價上漲X%", "出口禁令影響中國市場約X億美元營收", "資料中心營收首次超越遊戲部門").
- "Link1": MANDATORY. Provide a reliable source URL (NVIDIA IR, Reuters, Bloomberg, AnandTech, Tom's Hardware).
- Quantity: Aim for ~50 distinct high-impact events.
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


def generate_nvidia_events() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return

    client = genai.Client(api_key=api_key)
    print("Fetching NVIDIA AI hardware and business events (2012-Present)...")
    print("Sending request to Gemini 2.5 Flash with Google Search...")

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=PROMPT,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                response_modalities=["TEXT"],
            ),
        )

        csv_content = clean_csv(response.text)
        save_csv(csv_content, OUTPUT_FILE)

        print("-" * 50)
        print(csv_content[:800] + "\n...(truncated)")
        print("-" * 50)

    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    generate_nvidia_events()
