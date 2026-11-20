"""Load step: (re)build raw.pitches in DuckDB from every Parquet partition.

A full reload is fine at this stage: DuckDB reads millions of Parquet rows in
seconds. In Week 2 the dbt fact model becomes incremental, which is where
"only process new days" logic belongs.

`union_by_name=true` matters: Savant has added columns over the years (for
example bat-tracking fields in 2024), so older and newer files have different
schemas. Matching by name instead of position keeps them aligned.

Usage:
    python -m statcast_pipeline.load
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from statcast_pipeline import config

log = logging.getLogger(__name__)


def load_raw_pitches(
    raw_dir: Path | None = None,
    warehouse_path: Path | None = None,
) -> int:
    """Create or replace raw.pitches from all partitions. Returns the row count."""
    raw_dir = raw_dir or config.RAW_STATCAST_DIR
    warehouse_path = warehouse_path or config.WAREHOUSE_PATH

    files = sorted(raw_dir.glob(f"dt=*/{config.PARTITION_FILENAME}"))
    if not files:
        raise FileNotFoundError(
            f"No Parquet partitions under {raw_dir}. Run the extract step first."
        )

    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    glob = (raw_dir / "dt=*" / config.PARTITION_FILENAME).as_posix()

    with duckdb.connect(str(warehouse_path)) as con:
        con.execute("create schema if not exists raw")
        con.execute(
            f"""
            create or replace table raw.pitches as
            select *
            from read_parquet('{glob}', hive_partitioning = true, union_by_name = true)
            """
        )
        rows = con.execute("select count(*) from raw.pitches").fetchone()[0]
        days = con.execute("select count(distinct dt) from raw.pitches").fetchone()[0]

    log.info("Loaded raw.pitches: %s rows across %s game days from %s files",
             f"{rows:,}", days, len(files))
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_raw_pitches()


if __name__ == "__main__":
    main()
