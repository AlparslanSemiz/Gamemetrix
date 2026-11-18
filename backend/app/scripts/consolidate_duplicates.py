"""Merge duplicate game rows (verifying Steam ids first).

    python -m app.scripts.consolidate_duplicates            # dry-run (default)
    python -m app.scripts.consolidate_duplicates --apply

Dry-run prints the groups that would merge. --apply first verifies the Steam ids of
every game in a duplicate group against appdetails (refuted ids are cleared, so
they cannot travel), then merges and records 301 slug redirects.
"""

import argparse
import asyncio
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="verify ids, merge and write redirects")
    parser.add_argument("--no-verify", action="store_true", help="skip the Steam id verification pass")
    args = parser.parse_args(argv)

    from app.services.data_maintenance import run_duplicate_consolidation

    result = asyncio.run(run_duplicate_consolidation(dry_run=not args.apply, verify_steam=not args.no_verify))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
