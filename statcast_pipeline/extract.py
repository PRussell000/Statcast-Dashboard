"""Extract step: pull pitch-level Statcast data one game day at a time and write
it to a date-partitioned Parquet "data lake":

    data/raw/statcast/dt=2024-06-01/pitches.parquet
    data/raw/statcast/dt=2024-06-02/pitches.parquet
    ...

Design choices worth being able to explain in an interview:

* One day per request. Baseball Savant caps rows per query, so day-sized
  pulls avoid silently truncated results.
* Idempotent. Re-running a date replaces exactly that partition (written to a
  temp file, then atomically renamed), so retries and backfills never create
  duplicates.
* Retries with exponential backoff, because the source is a scraped web
  endpoint that times out now and then.
* Days with no games (off-season, All-Star break) write nothing and are logged.

Usage:
    python -m statcast_pipeline.extract --start 2024-06-01 --end 2024-06-07
    python -m statcast_pipeline.extract --start 2024-06-01 --end 2024-06-07 --force
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from tenacity import (
    before_sleep_log,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from statcast_pipeline import config
from statcast_pipeline.storage import write_parquet_atomic

log = logging.getLogger(__name__)

FetchFn = Callable[[date], pd.DataFrame]


def daterange(start: date, end: date) -> Iterator[date]:
    """Yield each date from start to end, inclusive."""
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start})")
    for offset in range((end - start).days + 1):
        yield start + timedelta(days=offset)


def partition_dir(day: date, base: Path | None = None) -> Path:
    base = base or config.RAW_STATCAST_DIR
    return base / f"dt={day.isoformat()}"


def partition_path(day: date, base: Path | None = None, filename: str = config.PARTITION_FILENAME) -> Path:
    return partition_dir(day, base) / filename


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def fetch_day(day: date) -> pd.DataFrame:
    """Fetch one day of pitches from Baseball Savant via pybaseball."""
    # Imported here so tests (and CI) never need network access or pybaseball's
    # import-time side effects.
    from pybaseball import statcast

    iso = day.isoformat()
    df = statcast(start_dt=iso, end_dt=iso, verbose=False, parallel=False)
    return df if df is not None else pd.DataFrame()


def write_partition(
    df: pd.DataFrame, day: date, base: Path | None = None, source: str = "baseball_savant"
) -> Path | None:
    """Write one day's pitches to its partition, replacing any previous file.

    Returns the file path, or None when there were no pitches that day.
    """
    target = partition_path(day, base)

    if df.empty:
        # No games: make sure a stale file from an earlier run doesn't linger.
        if target.exists():
            target.unlink()
        log.info("%s: no pitches (no games scheduled?)", day)
        return None

    out = df.copy()
    out["_extracted_at"] = datetime.now(timezone.utc)
    out["_source"] = source

    write_parquet_atomic(out, target)
    log.info("%s: wrote %s pitches -> %s", day, f"{len(out):,}", target)
    return target


def extract_range(
    start: date,
    end: date,
    *,
    force: bool = False,
    fetch: FetchFn = fetch_day,
    base: Path | None = None,
    pause: float = 0.0,
    source: str = "baseball_savant",
) -> dict[str, int]:
    """Extract every day in [start, end]. Existing partitions are skipped unless
    force=True, which makes long backfills resumable after a failure."""
    stats = {"written": 0, "skipped_existing": 0, "no_games": 0, "pitches": 0}

    for day in daterange(start, end):
        if not force and partition_path(day, base).exists():
            stats["skipped_existing"] += 1
            log.debug("%s: already extracted, skipping", day)
            continue

        df = fetch(day)
        if pause:
            time.sleep(pause)
        if write_partition(df, day, base, source) is None:
            stats["no_games"] += 1
        else:
            stats["written"] += 1
            stats["pitches"] += len(df)

    log.info("Extract finished: %s", stats)
    return stats


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> None:
    yesterday = date.today() - timedelta(days=1)
    parser = argparse.ArgumentParser(description="Extract Statcast pitches to Parquet.")
    parser.add_argument("--start", type=_parse_date, default=yesterday, help="YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--end", type=_parse_date, default=None, help="YYYY-MM-DD (default: same as --start)")
    parser.add_argument("--force", action="store_true", help="Re-pull days that already have a partition")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if config.SAMPLE_MODE:
        from statcast_pipeline.sample import fake_fetch

        extract_range(args.start, args.end or args.start, force=True, fetch=fake_fetch, source="sample")
    else:
        extract_range(args.start, args.end or args.start, force=args.force)


if __name__ == "__main__":
    main()
