"""Verify every stored Steam app id against appdetails.

    python -m app.scripts.verify_steam_ids            # dry-run (default): report only
    python -m app.scripts.verify_steam_ids --apply    # stamp verified ids, clear refuted ones

Refuted ids are cleared together with the Steam score/price data fetched from the
wrong app, and the game is queued for admin review. Paced at ~1 request / 1.6 s;
resume a long run with --after-id (printed at the end), re-checks only happen after
--reverify-days.
"""

import argparse
import asyncio
import json
import sys


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="write verdicts to the database")
    parser.add_argument("--limit", type=int, default=None, help="max games to check this run")
    parser.add_argument("--after-id", type=int, default=0, help="resume after this game id")
    parser.add_argument("--delay", type=float, default=1.6, help="seconds between Steam requests (>= 1.0)")
    parser.add_argument("--reverify-days", type=int, default=90, help="skip ids verified more recently")
    parser.add_argument("--all", action="store_true", help="ignore the verification stamp and check everything")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    from app.database import SessionLocal
    from app.services.steam_id_audit import audit_steam_ids

    if args.delay < 1.0:
        raise SystemExit("--delay must be at least 1.0 second (Steam store rate limit).")
    with SessionLocal() as db:
        report = await audit_steam_ids(
            db,
            apply=args.apply,
            limit=args.limit,
            after_id=args.after_id,
            delay_seconds=args.delay,
            reverify_days=None if args.all else args.reverify_days,
        )
    payload = {
        "mode": "apply" if report.apply else "dry-run",
        "checked": report.checked,
        "counts": report.counts,
        "stopped_early": report.stopped_early,
        "last_id": report.last_id,
        "findings": [vars(item) for item in report.findings],
    }
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"mode={payload['mode']} checked={report.checked} counts={report.counts}")
        print(f"resume with --after-id {report.last_id}")
        if report.stopped_early:
            print(f"STOPPED: {report.stopped_early}")
        for item in report.findings:
            print(
                f"{item.verdict:12} game={item.game_id} {item.slug!r} "
                f"steam={item.steam_app_id} ({item.steam_name or '-'}): {item.reason}"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_arguments(argv)))


if __name__ == "__main__":
    sys.exit(main())
