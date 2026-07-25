"""Run one recorded data-fill cycle from the command line."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-total", type=int, default=50_000)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh records even when their normal freshness window has not elapsed.",
    )
    return parser.parse_args()


async def _run(target_total: int, force: bool) -> None:
    from app.services.data_fill import execute_data_fill_run, queue_data_fill_run
    from app.services.data_fill.runs import load_run

    if target_total < 1 or target_total > 250_000:
        raise ValueError("--target-total must be between 1 and 250000.")
    queued = queue_data_fill_run(force=force, target_total=target_total)
    run_id = int(queued["id"])
    print(f"data_fill_run_id={run_id}", flush=True)
    await execute_data_fill_run(run_id, force=force, target_total=target_total)
    completed = load_run(run_id)
    print(json.dumps(completed, ensure_ascii=False, default=str), flush=True)


def main() -> None:
    args = _arguments()
    asyncio.run(_run(args.target_total, args.force))


if __name__ == "__main__":
    main()
