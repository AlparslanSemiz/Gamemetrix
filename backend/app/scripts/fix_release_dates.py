"""Fix 1970-01-01 release dates and original/remaster date mix-ups using Steam appdetails.

    python -m app.scripts.fix_release_dates                 # dry-run (default), 1970 rows only
    python -m app.scripts.fix_release_dates --scan-all      # also look for original-vs-remaster mix-ups
    python -m app.scripts.fix_release_dates --apply

Only `unknown` (1970) and `earlier` (Steam date 2+ years before ours, not a remaster) are
written; `conflict` rows are listed for a human. Steam dates are used only when appdetails
passes the same identity check as verify_steam_ids.
"""

import argparse
import asyncio
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="write the fixes")
    parser.add_argument("--scan-all", action="store_true", help="check every game with a Steam id")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=1.6, help="seconds between Steam requests (>= 1.0)")
    args = parser.parse_args(argv)
    if args.delay < 1.0:
        raise SystemExit("--delay must be at least 1.0 second (Steam store rate limit).")

    from app.database import SessionLocal
    from app.services.release_date_repair import repair_release_dates

    async def run() -> None:
        with SessionLocal() as db:
            report = await repair_release_dates(
                db, apply=args.apply, scan_all=args.scan_all, limit=args.limit, delay_seconds=args.delay
            )
        print(f"mode={'apply' if args.apply else 'dry-run'} checked={report.checked} counts={report.counts}")
        for change in report.changes:
            print(f"{change.kind:18} game={change.game_id} {change.slug!r} {change.old} -> {change.new}")

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
