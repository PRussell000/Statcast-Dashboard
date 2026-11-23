"""Load step: (re)build the raw tables in DuckDB from the Parquet lake.

    raw.pitches         <- data/raw/statcast/dt=*/pitches.parquet      (required)
    raw.games           <- data/raw/games/dt=*/games.parquet
    raw.game_officials  <- data/raw/game_officials/dt=*/officials.parquet
    raw.players         <- data/raw/players/players.parquet

A full reload is fine at this scale: DuckDB reads millions of Parquet rows in
seconds, and the dbt fact model is incremental, so transformation work stays
small. Optional sources that haven't been extracted yet get an empty table with
the right columns, so dbt can always build.

`union_by_name=true` matters: Savant has added columns over the years (for
example bat-tracking fields in 2024), so older and newer files have different
schemas. Matching by name instead of position keeps them aligned.

Usage:
    python -m statcast_pipeline.load
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

from statcast_pipeline import config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawTable:
    name: str
    pattern: str          # glob relative to the data dir
    partitioned: bool
    required: bool
    empty_ddl: str = ""   # columns for an empty placeholder table


def raw_tables(data_dir: Path) -> list[RawTable]:
    raw = data_dir / "raw"
    return [
        RawTable("pitches", (raw / "statcast" / "dt=*" / config.PARTITION_FILENAME).as_posix(),
                 partitioned=True, required=True),
        RawTable("games", (raw / "games" / "dt=*" / config.GAMES_FILENAME).as_posix(),
                 partitioned=True, required=False, empty_ddl="""
                    game_pk bigint, official_date varchar, game_datetime_utc varchar, game_type varchar,
                    status varchar, home_team_id bigint, home_team_name varchar, away_team_id bigint,
                    away_team_name varchar, venue_name varchar, double_header varchar, game_number bigint,
                    _extracted_at timestamptz, dt date"""),
        RawTable("game_officials", (raw / "game_officials" / "dt=*" / config.OFFICIALS_FILENAME).as_posix(),
                 partitioned=True, required=False, empty_ddl="""
                    game_pk bigint, official_id bigint, official_name varchar, official_type varchar,
                    _extracted_at timestamptz, dt date"""),
        RawTable("players", (raw / "players" / "players.parquet").as_posix(),
                 partitioned=False, required=False, empty_ddl="""
                    key_mlbam bigint, name_first varchar, name_last varchar, key_fangraphs bigint,
                    key_bbref varchar, key_retro varchar, mlb_played_first double, mlb_played_last double,
                    _extracted_at timestamptz"""),
    ]


def _has_files(pattern: str) -> bool:
    p = Path(pattern)
    # Find the first path component containing a wildcard and glob from its parent.
    parts = p.parts
    for i, part in enumerate(parts):
        if "*" in part:
            return any(Path(*parts[:i]).glob(str(Path(*parts[i:]))))
    return p.exists()


def load_all(data_dir: Path | None = None, warehouse: Path | str | None = None) -> dict[str, int]:
    """Create or replace every raw table. Returns row counts by table.

    `warehouse` is a DuckDB file path or a MotherDuck "md:<db>" string. With
    MotherDuck, DuckDB reads the local Parquet files and uploads the result.
    """
    data_dir = data_dir or config.DATA_DIR
    target = str(warehouse or config.WAREHOUSE_URI)
    if not target.startswith("md:"):
        Path(target).parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    with duckdb.connect(target) as con:
        con.execute("create schema if not exists raw")
        for t in raw_tables(data_dir):
            if _has_files(t.pattern):
                opts = "hive_partitioning = true, union_by_name = true" if t.partitioned else "union_by_name = true"
                con.execute(f"create or replace table raw.{t.name} as "
                            f"select * from read_parquet('{t.pattern}', {opts})")
            elif t.required:
                raise FileNotFoundError(f"No files match {t.pattern}. Run the extract step first.")
            else:
                log.warning("raw.%s: no files yet, creating an empty table", t.name)
                con.execute(f"create or replace table raw.{t.name} ({t.empty_ddl})")
            counts[t.name] = con.execute(f"select count(*) from raw.{t.name}").fetchone()[0]

    log.info("Loaded raw tables: %s", {k: f"{v:,}" for k, v in counts.items()})
    return counts


def load_raw_pitches(raw_dir: Path | None = None, warehouse_path: Path | None = None) -> int:
    """Backwards-compatible helper used by the Week 1 tests: load pitches only."""
    raw_dir = raw_dir or config.RAW_STATCAST_DIR
    warehouse_path = warehouse_path or config.WAREHOUSE_PATH
    pattern = (raw_dir / "dt=*" / config.PARTITION_FILENAME).as_posix()
    if not _has_files(pattern):
        raise FileNotFoundError(f"No Parquet partitions under {raw_dir}. Run the extract step first.")
    warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(warehouse_path)) as con:
        con.execute("create schema if not exists raw")
        con.execute(f"create or replace table raw.pitches as select * from read_parquet('{pattern}', "
                    "hive_partitioning = true, union_by_name = true)")
        return con.execute("select count(*) from raw.pitches").fetchone()[0]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_all()


if __name__ == "__main__":
    main()
