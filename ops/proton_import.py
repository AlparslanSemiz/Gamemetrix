#!/usr/bin/env python3
"""
Stream a large ProtonDB JSON dump and update GameMetrix SQLite rows.

This script is designed for low-memory hosts:
  * it uses ijson, never json.load();
  * it only keeps one small aggregate per matched Steam app id;
  * it writes SQLite updates in committed batches;
  * it reports peak RSS and exits non-zero if --max-rss-mb is exceeded.

The current local SQLite catalog does not have a games.steam_appid column, so
the importer uses it when present and otherwise resolves Steam ids from
external_ids plus Steam CDN URLs in cover_url/image_url.
"""

from __future__ import annotations

import argparse
import re
import resource
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import ijson
except ImportError:
    sys.exit(
        "ijson is required. On Ubuntu: sudo apt-get install python3-ijson"
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = REPO_ROOT / "data" / "reports_piiremoved.json"
DEFAULT_DB = REPO_ROOT / "backend" / "gamemetrix.dev.db"

STEAM_APP_URL_RE = re.compile(r"steam/apps/(\d+)/")
STEAM_STORE_URL_RE = re.compile(r"(?:store\.steampowered\.com/app/|steam/app/)(\d+)")

TIER_SCORES = {
    "platinum": 100.0,
    "gold": 80.0,
    "silver": 60.0,
    "bronze": 40.0,
    "borked": 0.0,
}

FAULT_FIELDS = (
    "audioFaults",
    "graphicalFaults",
    "inputFaults",
    "performanceFaults",
    "saveGameFaults",
    "stabilityFaults",
    "windowingFaults",
)


@dataclass(slots=True)
class AppStats:
    count: int = 0
    score_sum: float = 0.0

    def add(self, score: float) -> None:
        self.count += 1
        self.score_sum += score

    def aggregate(self) -> tuple[str, float]:
        score = round(self.score_sum / self.count, 1)
        return tier_from_score(score), score


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def clamp_score(score: float) -> float:
    return max(0.0, min(100.0, score))


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"yes", "true", "1", "y"}


def falsy(value: Any) -> bool:
    return str(value).strip().lower() in {"no", "false", "0", "n"}


def normalize_app_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return text
    match = STEAM_STORE_URL_RE.search(text)
    return match.group(1) if match else None


def tier_from_score(score: float) -> str:
    if score >= 90:
        return "platinum"
    if score >= 75:
        return "gold"
    if score >= 60:
        return "silver"
    if score >= 40:
        return "bronze"
    return "borked"


def iter_reports(path: Path):
    with path.open("rb") as fh:
        first = b""
        while not first:
            chunk = fh.read(1)
            if not chunk:
                break
            if not chunk.isspace():
                first = chunk

    prefix = "item" if first == b"[" else "reports.item"
    with path.open("rb") as fh:
        yield from ijson.items(fh, prefix)


def extract_app_id(report: dict[str, Any]) -> str | None:
    app_id = normalize_app_id(report.get("appId"))
    if app_id:
        return app_id

    app = report.get("app") or {}
    steam = app.get("steam") or {}
    app_id = normalize_app_id(steam.get("appId"))
    if app_id:
        return app_id

    responses = report.get("responses") or {}
    return normalize_app_id(responses.get("answerToWhatGame"))


def extract_explicit_tier(report: dict[str, Any]) -> str | None:
    responses = report.get("responses") or {}
    for candidate in (
        report.get("proton_tier"),
        report.get("protonTier"),
        report.get("tier"),
        report.get("rating"),
        responses.get("proton_tier"),
        responses.get("protonTier"),
        responses.get("tier"),
        responses.get("rating"),
    ):
        if isinstance(candidate, str) and candidate.lower() in TIER_SCORES:
            return candidate.lower()
    return None


def extract_explicit_score(report: dict[str, Any]) -> float | None:
    responses = report.get("responses") or {}
    for candidate in (
        report.get("proton_score"),
        report.get("protonScore"),
        report.get("score"),
        responses.get("proton_score"),
        responses.get("protonScore"),
        responses.get("score"),
    ):
        try:
            score = float(candidate)
        except (TypeError, ValueError):
            continue
        if 0.0 <= score <= 1.0:
            score *= 100.0
        return clamp_score(score)
    return None


def score_raw_report(report: dict[str, Any]) -> float | None:
    responses = report.get("responses") or {}
    verdict = str(responses.get("verdict") or "").strip().lower()

    if verdict == "yes":
        score = 100.0
        if falsy(responses.get("installs")):
            score -= 35.0
        if falsy(responses.get("opens")):
            score -= 30.0
        if falsy(responses.get("startsPlay")):
            score -= 25.0

        for field in FAULT_FIELDS:
            if truthy(responses.get(field)):
                score -= 6.0
        if truthy(responses.get("significantBugs")):
            score -= 18.0
        if truthy(responses.get("extra")):
            score -= 4.0
        if truthy(responses.get("customizationsUsed")):
            score -= 4.0
        if truthy(responses.get("launchFlagsUsed")):
            score -= 3.0
        if truthy(responses.get("isImpactedByAntiCheat")):
            score -= 15.0 if truthy(responses.get("isMultiplayerImportant")) else 7.0

        duration = str(responses.get("duration") or "").strip()
        if duration == "lessThanAnHour":
            score -= 4.0
        elif duration == "moreThanTenHours":
            score += 2.0

        return clamp_score(score)

    if verdict == "no":
        score = 0.0
        if truthy(responses.get("installs")):
            score += 10.0
        if truthy(responses.get("opens")):
            score += 12.0
        if truthy(responses.get("startsPlay")):
            score += 15.0
        return clamp_score(min(score, 39.0))

    return None


def score_report(report: dict[str, Any]) -> float | None:
    explicit_score = extract_explicit_score(report)
    if explicit_score is not None:
        return explicit_score

    explicit_tier = extract_explicit_tier(report)
    if explicit_tier is not None:
        return TIER_SCORES[explicit_tier]

    return score_raw_report(report)


def table_exists(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}


def ensure_schema(db: sqlite3.Connection) -> None:
    if not table_exists(db, "games"):
        raise RuntimeError("Database does not contain a games table")

    columns = table_columns(db, "games")
    if "proton_tier" not in columns:
        db.execute("ALTER TABLE games ADD COLUMN proton_tier VARCHAR(16)")
    if "proton_score" not in columns:
        db.execute("ALTER TABLE games ADD COLUMN proton_score FLOAT")
    db.commit()


def add_mapping(mapping: dict[str, int], app_id: Any, game_id: int) -> None:
    normalized = normalize_app_id(app_id)
    if normalized:
        mapping[normalized] = int(game_id)


def build_appid_to_game_id(db: sqlite3.Connection) -> dict[str, int]:
    if not table_exists(db, "games"):
        raise RuntimeError("Database does not contain a games table")

    mapping: dict[str, int] = {}
    columns = table_columns(db, "games")

    for column in ("steam_appid", "steam_app_id", "steam_id"):
        if column in columns:
            for game_id, app_id in db.execute(
                f"SELECT id, {column} FROM games WHERE {column} IS NOT NULL"
            ):
                add_mapping(mapping, app_id, game_id)

    url_columns = [column for column in ("cover_url", "image_url") if column in columns]
    if url_columns:
        selected = ", ".join(["id", *url_columns])
        for row in db.execute(f"SELECT {selected} FROM games"):
            game_id = row[0]
            for url in row[1:]:
                match = STEAM_APP_URL_RE.search(url or "")
                if match:
                    mapping[match.group(1)] = int(game_id)
                    break

    if table_exists(db, "external_ids"):
        ext_columns = table_columns(db, "external_ids")
        if {"game_id", "external_id", "source"}.issubset(ext_columns):
            for game_id, external_id in db.execute(
                "SELECT game_id, external_id FROM external_ids WHERE lower(source) = 'steam'"
            ):
                add_mapping(mapping, external_id, game_id)

    return mapping


def update_batches(
    db: sqlite3.Connection,
    rows: list[tuple[str, float, int]],
) -> int:
    cursor = db.cursor()
    cursor.executemany(
        "UPDATE games SET proton_tier = ?, proton_score = ? WHERE id = ?",
        rows,
    )
    db.commit()
    return cursor.rowcount if cursor.rowcount >= 0 else len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream ProtonDB JSON into SQLite")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-rss-mb", type=float, default=50.0)
    parser.add_argument("--progress-every", type=int, default=200_000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inspect", type=int, metavar="N")
    args = parser.parse_args()

    json_path = args.json.expanduser().resolve()
    db_path = args.db.expanduser().resolve()

    if not json_path.is_file():
        sys.exit(f"JSON file not found: {json_path}")
    if not db_path.is_file():
        sys.exit(f"Database not found: {db_path}")

    if args.inspect:
        import json

        for index, report in enumerate(iter_reports(json_path), 1):
            print(json.dumps(report, indent=2)[:2000])
            if index >= args.inspect:
                break
        print(f"peak RSS: {rss_mb():.1f} MB")
        return 0

    db = sqlite3.connect(db_path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA cache_size=-8000")

        appid_to_game = build_appid_to_game_id(db)
        print(f"database: {db_path}")
        print(f"json: {json_path}")
        print(f"games with resolvable Steam app ids: {len(appid_to_game):,}")

        if not appid_to_game:
            print("No Steam app id mapping found in this database.")
            return 1

        stats_by_app: dict[str, AppStats] = {}
        seen = matched = scored = 0

        for report in iter_reports(json_path):
            seen += 1
            app_id = extract_app_id(report)
            if app_id is None or app_id not in appid_to_game:
                continue

            matched += 1
            score = score_report(report)
            if score is None:
                continue

            stats_by_app.setdefault(app_id, AppStats()).add(score)
            scored += 1

            if seen % args.progress_every == 0:
                peak = rss_mb()
                print(
                    f"  {seen:,} reports read, {matched:,} matched, "
                    f"{scored:,} scored, RSS {peak:.1f} MB"
                )
                if peak > args.max_rss_mb:
                    print("ERROR: memory budget exceeded", file=sys.stderr)
                    return 2

        print(
            f"reports read: {seen:,} | matched to catalog: {matched:,} | "
            f"scored: {scored:,}"
        )
        print(f"apps with ProtonDB data: {len(stats_by_app):,}")

        if not stats_by_app:
            print("Nothing to update.")
            return 1

        if args.dry_run:
            for index, (app_id, stats) in enumerate(stats_by_app.items(), 1):
                tier, score = stats.aggregate()
                print(
                    f"  would set app_id={app_id}, game_id={appid_to_game[app_id]}: "
                    f"proton_tier={tier}, proton_score={score}"
                )
                if index >= 10:
                    break
            print(f"dry-run: {len(stats_by_app):,} games would be updated")
        else:
            ensure_schema(db)
            updated = 0
            batch: list[tuple[str, float, int]] = []
            for app_id, stats in stats_by_app.items():
                tier, score = stats.aggregate()
                batch.append((tier, score, appid_to_game[app_id]))
                if len(batch) >= args.batch_size:
                    updated += update_batches(db, batch)
                    batch.clear()
            if batch:
                updated += update_batches(db, batch)
            print(f"updated {updated:,} games")

        peak = rss_mb()
        print(f"peak RSS: {peak:.1f} MB (limit {args.max_rss_mb:.0f} MB)")
        if peak > args.max_rss_mb:
            print("ERROR: memory budget exceeded", file=sys.stderr)
            return 2
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
