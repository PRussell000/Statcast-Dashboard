"""Backfill whole seasons: pitches, games and umpires for every day from mid-March
to early November, then one load + dbt build at the end.

It is resumable: days already on disk are skipped, so if it dies at 2 a.m. just
run the same command again. Expect roughly 5-20 seconds per day for the
Statcast pull, i.e. about 1-1.5 hours per season. Start with 2-3 recent seasons
and run the rest overnight.

Usage:
    python -m statcast_pipeline.backfill --seasons 2023 2024 2025
    python -m statcast_pipeline.backfill --from-season 2015 --to-season 2025
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

from statcast_pipeline import config
from statcast_pipeline.extract import extract_range
from statcast_pipeline.extract_games import extract_games_range
from statcast_pipeline.extract_players import extract_players
from statcast_pipeline.load import load_all
from statcast_pipeline.publish import publish
from statcast_pipeline.transform import dbt_build

log = logging.getLogger(__name__)

FIRST_STATCAST_SEASON = 2015


def season_window(season: int) -> tuple[date, date]:
    """Late spring training through the end of the postseason. Days without
    games are cheap: they're logged and skipped."""
    start, end = date(season, 3, 15), date(season, 11, 10)
    return start, min(end, date.today())


def backfill(seasons: list[int], *, force: bool = False, pause: float = config.DEFAULT_PAUSE_SECONDS,
             build: bool = True, extract_only: bool = False) -> None:
    for season in sorted(seasons):
        if season < FIRST_STATCAST_SEASON:
            log.warning("Skipping %s: Statcast pitch tracking starts in %s", season, FIRST_STATCAST_SEASON)
            continue
        start, end = season_window(season)
        if start > end:
            log.warning("Skipping %s: season hasn't started yet", season)
            continue
        log.info("=== Season %s: %s to %s ===", season, start, end)
        if config.SAMPLE_MODE:
            from statcast_pipeline import sample

            extract_range(start, end, force=True, fetch=sample.fake_fetch, source="sample")
            extract_games_range(start, end, force=True, fetch=sample.fake_fetch_schedule,
                                fetch_officials=sample.fake_fetch_boxscore_officials)
        else:
            extract_range(start, end, force=force, pause=pause)
            extract_games_range(start, end, force=force, pause=pause)

    if extract_only:
        return

    try:
        extract_players()
    except Exception as exc:
        log.warning("Player register refresh failed (%s)", exc)

    load_all()
    if build:
        dbt_build()
        publish()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Backfill whole Statcast seasons.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seasons", type=int, nargs="+")
    group.add_argument("--from-season", type=int)
    parser.add_argument("--to-season", type=int, default=date.today().year)
    parser.add_argument("--force", action="store_true", help="Re-pull days already on disk")
    parser.add_argument("--pause", type=float, default=config.DEFAULT_PAUSE_SECONDS,
                        help="Seconds to wait between days (default 1)")
    parser.add_argument("--skip-dbt", action="store_true")
    parser.add_argument("--extract-only", action="store_true",
                        help="Only extract; Airflow runs players, load and dbt as separate tasks")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    seasons = args.seasons or list(range(args.from_season, args.to_season + 1))
    backfill(seasons, force=args.force, pause=args.pause, build=not args.skip_dbt,
             extract_only=args.extract_only)


if __name__ == "__main__":
    main()
