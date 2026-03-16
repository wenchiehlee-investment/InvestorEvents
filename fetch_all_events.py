"""
Run all event fetchers in sequence.
Usage:
    python fetch_all_events.py              # run all
    python fetch_all_events.py crashes ai   # run specific fetchers
Available keys: crashes, stock, ai, nvidia, earnings
"""

import sys
from fetch_historical_crashes import generate_historical_crashes
from fetch_stock_events import generate_stock_events
from fetch_ai_events import generate_ai_events
from fetch_nvidia_events import generate_nvidia_events
from fetch_upcoming_earnings import generate_upcoming_earnings

FETCHERS = {
    "crashes":  ("歷史股市崩盤事件",    generate_historical_crashes),
    "stock":    ("重要股市事件",         generate_stock_events),
    "ai":       ("重要AI事件",           generate_ai_events),
    "nvidia":   ("NVIDIA AI硬體事件",    generate_nvidia_events),
    "earnings": ("未來30天財報/法說會",  generate_upcoming_earnings),
}


def main() -> None:
    keys = sys.argv[1:] if len(sys.argv) > 1 else list(FETCHERS)
    invalid = [k for k in keys if k not in FETCHERS]
    if invalid:
        print(f"Unknown fetcher(s): {invalid}")
        print(f"Available: {list(FETCHERS)}")
        sys.exit(1)

    for key in keys:
        label, fn = FETCHERS[key]
        print(f"\n{'='*50}")
        print(f"  [{key}] {label}")
        print(f"{'='*50}")
        fn()

    print("\nAll done.")


if __name__ == "__main__":
    main()
