from __future__ import annotations

from pathlib import Path

from src.browser import SnapshotParser


if __name__ == "__main__":
    snapshot = Path("logs/debug/latest_snapshot.txt").read_text(encoding="utf-8")
    parser = SnapshotParser(snapshot)
    print("search_input:", getattr(parser.find_input_by_keywords(["搜索", "职位"]), "uid", ""))
    print("job_cards:", len(parser.find_job_cards()))
    print("communicate_button:", getattr(parser.find_communication_button(), "uid", ""))
