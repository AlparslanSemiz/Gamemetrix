"""Download the latest ProtonDB report archive for later Postgres import."""

from __future__ import annotations

import os
import json
from pathlib import Path
from urllib.request import Request, urlopen

REPO_OWNER = "bdefore"
REPO_NAME = "protondb-data"
FOLDER_PATH = "reports"
SAVE_DIR = Path(os.getenv("PROTON_REPORT_DIR", "downloads"))
LAST_FILE_TRACKER = SAVE_DIR / "last_downloaded.txt"


def get_latest_report() -> tuple[str, str] | None:
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{FOLDER_PATH}"
    request = Request(url, headers={"User-Agent": "GameMetrix/0.1"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    report_files = [
        item for item in payload
        if isinstance(item, dict) and str(item.get("name", "")).endswith(".tar.gz")
    ]
    if not report_files:
        return None
    latest_file = sorted(report_files, key=lambda item: str(item["name"]))[-1]
    return str(latest_file["name"]), str(latest_file["download_url"])


def download_file(url: str, filename: str) -> Path:
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    local_path = SAVE_DIR / filename
    request = Request(url, headers={"User-Agent": "GameMetrix/0.1"})
    with urlopen(request, timeout=60) as response:
        with local_path.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return local_path


def main() -> None:
    result = get_latest_report()
    if not result:
        print("No ProtonDB report archive found.")
        return

    filename, download_url = result
    last_downloaded = LAST_FILE_TRACKER.read_text().strip() if LAST_FILE_TRACKER.exists() else ""
    if filename == last_downloaded:
        print(f"Already downloaded latest ProtonDB report: {filename}")
        return

    local_path = download_file(download_url, filename)
    LAST_FILE_TRACKER.write_text(filename)
    print(f"Downloaded {filename} to {local_path}")


if __name__ == "__main__":
    main()
