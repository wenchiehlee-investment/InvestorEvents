"""Compatibility entrypoint; all producer logic lives in the shared skill."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "skills" /
            "skill-stock-investorevent-fetch" / "scripts" / "fetch_all_events.py"),
        run_name="__main__",
    )
