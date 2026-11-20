"""Run the whole pipeline once: extract -> load -> dbt build.

This is the single command Docker runs. In Week 3, Airflow replaces this file
by calling the same three steps as separate tasks with retries and alerts.

Usage:
    python -m statcast_pipeline.run --start 2024-06-01 --end 2024-06-07
    python -m statcast_pipeline.run --sample   # offline demo with fake data
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
from statcast_pipeline.load import load_raw_pitches

log = logging.getLogger(__name__)


def dbt_build() -> None:
    env = {**os.environ, "WAREHOUSE_PATH": str(config.WAREHOUSE_PATH)}
    cmd = [
        "dbt", "build",
        "--project-dir", str(config.DBT_PROJECT_DIR),
        "--profiles-dir", str(config.DBT_PROJECT_DIR),
    ]
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env)


def main(argv: list[str] | None = None) -> None:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Run extract -> load -> dbt build.")
    parser.add_argument("--start", type=date.fromisoformat, default=yesterday)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--force", action="store_true", help="Re-pull existing days")
    parser.add_argument("--sample", action="store_true",
                        help="Use generated fake data instead of Baseball Savant (offline demo / CI)")
    parser.add_argument("--skip-dbt", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.sample:
        from statcast_pipeline.sample import fake_fetch
        extract_range(args.start, args.end or args.start, force=True, fetch=fake_fetch)
    else:
        extract_range(args.start, args.end or args.start, force=args.force)

    load_raw_pitches()

    if not args.skip_dbt:
        try:
            dbt_build()
        except subprocess.CalledProcessError as exc:
            log.error("dbt build failed (exit %s)", exc.returncode)
            sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
