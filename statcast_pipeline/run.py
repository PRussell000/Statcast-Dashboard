"""Run the whole pipeline once:

    extract pitches -> extract games + umpires -> refresh players -> load -> dbt build

This is the single command Docker runs. In Week 3, Airflow calls the same steps
as separate tasks with retries and alerts.

Usage:
    python -m statcast_pipeline.run --start 2024-06-01 --end 2024-06-07
    python -m statcast_pipeline.run --sample --start 2024-06-01 --end 2024-06-07   # offline demo
    python -m statcast_pipeline.run --full-refresh ...   # rebuild incremental dbt models from scratch
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date, timedelta

from statcast_pipeline import config
from statcast_pipeline.extract import extract_range
from statcast_pipeline.extract_games import extract_games_range
from statcast_pipeline.extract_players import extract_players
from statcast_pipeline.load import load_all

log = logging.getLogger(__name__)


def dbt_build(full_refresh: bool = False) -> None:
    env = {**os.environ, "WAREHOUSE_PATH": str(config.WAREHOUSE_PATH)}
    cmd = [
        "dbt", "build",
        "--project-dir", str(config.DBT_PROJECT_DIR),
        "--profiles-dir", str(config.DBT_PROJECT_DIR),
    ]
    if full_refresh:
        cmd.append("--full-refresh")
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def extract_all(start: date, end: date, *, force: bool, sample: bool, pause: float = 0.0) -> None:
    if sample:
        from statcast_pipeline import sample as s

        extract_range(start, end, force=True, fetch=s.fake_fetch)
        extract_games_range(start, end, force=True, fetch=s.fake_fetch_schedule,
                            fetch_officials=s.fake_fetch_boxscore_officials)
        extract_players(force=True, fetch=lambda: s.fake_players_from_lake(config.RAW_STATCAST_DIR))
        return

    extract_range(start, end, force=force, pause=pause)
    extract_games_range(start, end, force=force, pause=pause)
    try:
        extract_players(force=False)
    except Exception as exc:  # names are nice to have; never block the pipeline on them
        log.warning("Player register refresh failed (%s); continuing with the existing copy", exc)


def main(argv: list[str] | None = None) -> None:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Run extract -> load -> dbt build.")
    parser.add_argument("--start", type=date.fromisoformat, default=yesterday)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--force", action="store_true", help="Re-pull existing days")
    parser.add_argument("--sample", action="store_true",
                        help="Use generated fake data instead of live sources (offline demo / CI)")
    parser.add_argument("--skip-dbt", action="store_true")
    parser.add_argument("--full-refresh", action="store_true", help="Pass --full-refresh to dbt")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    extract_all(args.start, args.end or args.start, force=args.force, sample=args.sample)
    load_all()

    if not args.skip_dbt:
        try:
            dbt_build(full_refresh=args.full_refresh)
        except subprocess.CalledProcessError as exc:
            log.error("dbt build failed (exit %s)", exc.returncode)
            sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
