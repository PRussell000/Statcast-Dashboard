"""Extract step for game metadata and umpires, from the MLB Stats API.

For each day this writes two partitions:

    data/raw/games/dt=YYYY-MM-DD/games.parquet               one row per game
    data/raw/game_officials/dt=YYYY-MM-DD/officials.parquet  one row per umpire per game

One schedule request per day returns every game with its umpires
(`hydrate=officials`). If a finished game comes back without umpires, we fall
back to that game's boxscore, which also lists them. The log reports coverage
("home-plate umpire found for 15/15 games") so gaps are visible.

Usage:
    python -m statcast_pipeline.extract_games --start 2024-06-01 --end 2024-06-07
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from statcast_pipeline import config
from statcast_pipeline.extract import daterange, partition_path
from statcast_pipeline.storage import write_parquet_atomic

log = logging.getLogger(__name__)

ScheduleFn = Callable[[date], dict[str, Any]]
OfficialsFn = Callable[[int], list[dict[str, Any]]]

HOME_PLATE = "Home Plate"
# Games that were never played have no umpires to look up. Everything else
# (including "Completed Early: Rain", "Final: Tied", suspended games) gets the
# boxscore fallback if the schedule came back without umpires.
NOT_PLAYED_PREFIXES = ("Postponed", "Cancelled", "Scheduled", "Pre-Game", "Warmup")


def _was_played(status: str | None) -> bool:
    return bool(status) and not status.startswith(NOT_PLAYED_PREFIXES)

_retry = retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)


@_retry
def fetch_schedule(day: date) -> dict[str, Any]:
    """All MLB games on one date, with umpires attached."""
    resp = requests.get(
        f"{config.MLB_STATSAPI_BASE}/schedule",
        params={"sportId": 1, "date": day.isoformat(), "hydrate": "officials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


@_retry
def fetch_boxscore_officials(game_pk: int) -> list[dict[str, Any]]:
    """Fallback: umpires for one game from its boxscore."""
    resp = requests.get(f"{config.MLB_STATSAPI_BASE}/game/{game_pk}/boxscore", timeout=30)
    resp.raise_for_status()
    return resp.json().get("officials", [])


def _official_rows(game_pk: int, officials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in officials or []:
        person = item.get("official") or {}
        if person.get("id") is None:
            continue
        rows.append({
            "game_pk": int(game_pk),
            "official_id": int(person["id"]),
            "official_name": person.get("fullName"),
            "official_type": item.get("officialType"),
        })
    return rows


def parse_schedule(
    payload: dict[str, Any],
    fetch_officials: OfficialsFn | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Turn a schedule response into (games, officials) DataFrames."""
    games, officials = [], []

    for day_block in payload.get("dates", []):
        for g in day_block.get("games", []):
            game_pk = int(g["gamePk"])
            status = (g.get("status") or {}).get("detailedState")
            teams = g.get("teams") or {}
            home = (teams.get("home") or {}).get("team") or {}
            away = (teams.get("away") or {}).get("team") or {}

            games.append({
                "game_pk": game_pk,
                "official_date": g.get("officialDate") or day_block.get("date"),
                "game_datetime_utc": g.get("gameDate"),
                "game_type": g.get("gameType"),
                "status": status,
                "home_team_id": home.get("id"),
                "home_team_name": home.get("name"),
                "away_team_id": away.get("id"),
                "away_team_name": away.get("name"),
                "venue_name": (g.get("venue") or {}).get("name"),
                "double_header": g.get("doubleHeader"),
                "game_number": g.get("gameNumber"),
            })

            rows = _official_rows(game_pk, g.get("officials", []))
            if not rows and fetch_officials and _was_played(status):
                rows = _official_rows(game_pk, fetch_officials(game_pk))
            officials.extend(rows)

    return pd.DataFrame(games), pd.DataFrame(officials)


def _write_or_clear(df: pd.DataFrame, target: Path) -> None:
    if df.empty:
        if target.exists():
            target.unlink()
        return
    out = df.copy()
    out["_extracted_at"] = datetime.now(timezone.utc)
    write_parquet_atomic(out, target)


def extract_games_range(
    start: date,
    end: date,
    *,
    force: bool = False,
    fetch: ScheduleFn = fetch_schedule,
    fetch_officials: OfficialsFn = fetch_boxscore_officials,
    games_base: Path | None = None,
    officials_base: Path | None = None,
    pause: float = 0.0,
) -> dict[str, int]:
    games_base = games_base or config.RAW_GAMES_DIR
    officials_base = officials_base or config.RAW_OFFICIALS_DIR
    stats = {"days_written": 0, "skipped_existing": 0, "games": 0, "games_with_plate_umpire": 0}

    for day in daterange(start, end):
        games_file = partition_path(day, games_base, config.GAMES_FILENAME)
        officials_file = partition_path(day, officials_base, config.OFFICIALS_FILENAME)

        if not force and games_file.exists():
            stats["skipped_existing"] += 1
            continue

        games, officials = parse_schedule(fetch(day), fetch_officials)
        if pause:
            time.sleep(pause)

        _write_or_clear(games, games_file)
        _write_or_clear(officials, officials_file)

        if games.empty:
            log.info("%s: no games scheduled", day)
            continue

        with_ump = 0 if officials.empty else officials.loc[
            officials["official_type"] == HOME_PLATE, "game_pk"].nunique()
        stats["days_written"] += 1
        stats["games"] += len(games)
        stats["games_with_plate_umpire"] += with_ump
        log.info("%s: %s games, home-plate umpire found for %s/%s", day, len(games), with_ump, len(games))

    log.info("Games extract finished: %s", stats)
    return stats


def days_missing_games(
    statcast_base: Path | None = None,
    games_base: Path | None = None,
) -> list[date]:
    """Days that have pitch data on disk but no games partition."""
    statcast_base = statcast_base or config.RAW_STATCAST_DIR
    games_base = games_base or config.RAW_GAMES_DIR
    days = sorted(date.fromisoformat(d.name.removeprefix("dt=")) for d in statcast_base.glob("dt=*") if d.is_dir())
    return [d for d in days if not partition_path(d, games_base, config.GAMES_FILENAME).exists()]


def fill_gaps(**kwargs: Any) -> dict[str, int]:
    """Extract games and umpires for every day that has pitches but no games yet."""
    missing = days_missing_games(kwargs.pop("statcast_base", None), kwargs.get("games_base"))
    log.info("Days with pitches but no games data: %s", len(missing))
    totals = {"days_written": 0, "skipped_existing": 0, "games": 0, "games_with_plate_umpire": 0}
    for day in missing:
        for k, v in extract_games_range(day, day, **kwargs).items():
            totals[k] += v
    return totals


def main(argv: list[str] | None = None) -> None:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Extract MLB games and umpires to Parquet.")
    parser.add_argument("--start", type=date.fromisoformat, default=yesterday)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--force", action="store_true", help="Re-pull days that already have games data")
    parser.add_argument("--fill-gaps", action="store_true",
                        help="Ignore --start/--end; extract every day that has pitches but no games data")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    kwargs: dict[str, Any] = {}
    if config.SAMPLE_MODE:
        from statcast_pipeline import sample

        kwargs = {"fetch": sample.fake_fetch_schedule, "fetch_officials": sample.fake_fetch_boxscore_officials}
    if args.fill_gaps:
        fill_gaps(**kwargs)
    else:
        extract_games_range(args.start, args.end or args.start, force=args.force or config.SAMPLE_MODE, **kwargs)


if __name__ == "__main__":
    main()
