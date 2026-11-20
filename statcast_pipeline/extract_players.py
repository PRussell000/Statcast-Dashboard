"""Extract step for player names and cross-site IDs (the Chadwick Bureau
register, via pybaseball). Statcast only carries the pitcher's name, so this is
what lets dim_players name batters too, and it adds FanGraphs / Baseball
Reference IDs for joining other data later.

The register changes slowly, so it is refreshed at most once every 7 days
unless --force is given.

Usage:
    python -m statcast_pipeline.extract_players [--force]
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from statcast_pipeline import config
from statcast_pipeline.storage import write_parquet_atomic

log = logging.getLogger(__name__)

MAX_AGE_SECONDS = 7 * 24 * 3600
PLAYER_COLUMNS = ["key_mlbam", "name_first", "name_last", "key_fangraphs", "key_bbref",
                  "key_retro", "mlb_played_first", "mlb_played_last"]


def fetch_register() -> pd.DataFrame:
    from pybaseball import chadwick_register

    return chadwick_register()


def is_fresh(path: Path, max_age: float = MAX_AGE_SECONDS) -> bool:
    return path.exists() and (time.time() - path.stat().st_mtime) < max_age


def extract_players(
    *,
    force: bool = False,
    fetch: Callable[[], pd.DataFrame] = fetch_register,
    target: Path | None = None,
) -> int | None:
    """Write the player register. Returns rows written, or None if skipped."""
    target = target or config.RAW_PLAYERS_PATH
    if not force and is_fresh(target):
        log.info("Player register is less than 7 days old; skipping (use --force to refresh)")
        return None

    df = fetch()
    df = df.loc[df["key_mlbam"].fillna(-1).astype("int64") > 0, PLAYER_COLUMNS].copy()
    df["_extracted_at"] = datetime.now(timezone.utc)
    write_parquet_atomic(df, target)
    log.info("Wrote %s players -> %s", f"{len(df):,}", target)
    return len(df)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract the Chadwick player register.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    extract_players(force=args.force)


if __name__ == "__main__":
    main()
