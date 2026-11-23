"""Central configuration. Paths can be overridden with environment variables,
which is how Docker and Airflow point the pipeline at mounted volumes.

Environment variables:
    DATA_DIR         where the Parquet lake lives (default: ./data)
    WAREHOUSE_PATH   a DuckDB file path, or "md:<database>" for MotherDuck
                     (default: ./warehouse/statcast.duckdb). MotherDuck also
                     needs MOTHERDUCK_TOKEN set.
    STATCAST_SAMPLE  "1" = use generated sample data in data_sample/ and
                     warehouse/sample.duckdb (offline demos, CI, DAG tests)
    PAUSE_SECONDS    pause between days during backfills (default 1)
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
RAW_STATCAST_DIR = DATA_DIR / "raw" / "statcast"
RAW_GAMES_DIR = DATA_DIR / "raw" / "games"
RAW_OFFICIALS_DIR = DATA_DIR / "raw" / "game_officials"
RAW_PLAYERS_PATH = DATA_DIR / "raw" / "players" / "players.parquet"

_warehouse_env = os.environ.get("WAREHOUSE_PATH", "")
if _warehouse_env.startswith("md:"):
    # MotherDuck: a connection string, not a file on disk.
    WAREHOUSE_URI = _warehouse_env
    WAREHOUSE_PATH = PROJECT_ROOT / "warehouse" / "statcast.duckdb"  # unused for md:
else:
    WAREHOUSE_PATH = Path(_warehouse_env or PROJECT_ROOT / "warehouse" / "statcast.duckdb")
    WAREHOUSE_URI = str(WAREHOUSE_PATH)

DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"

# Name of the Parquet file written inside each date partition.
PARTITION_FILENAME = "pitches.parquet"
GAMES_FILENAME = "games.parquet"
OFFICIALS_FILENAME = "officials.parquet"

MLB_STATSAPI_BASE = "https://statsapi.mlb.com/api/v1"

# Seconds to wait between days during long backfills, to be polite to the sources.
DEFAULT_PAUSE_SECONDS = float(os.environ.get("PAUSE_SECONDS", "1.0"))

SAMPLE_MODE = False


def is_motherduck() -> bool:
    return WAREHOUSE_URI.startswith("md:")


def use_sample_paths() -> None:
    """Point every path at a separate sandbox so generated sample data can never
    mix with real data: data_sample/ and warehouse/sample.duckdb."""
    global DATA_DIR, RAW_STATCAST_DIR, RAW_GAMES_DIR, RAW_OFFICIALS_DIR, RAW_PLAYERS_PATH
    global WAREHOUSE_PATH, WAREHOUSE_URI, SAMPLE_MODE
    DATA_DIR = PROJECT_ROOT / "data_sample"
    RAW_STATCAST_DIR = DATA_DIR / "raw" / "statcast"
    RAW_GAMES_DIR = DATA_DIR / "raw" / "games"
    RAW_OFFICIALS_DIR = DATA_DIR / "raw" / "game_officials"
    RAW_PLAYERS_PATH = DATA_DIR / "raw" / "players" / "players.parquet"
    WAREHOUSE_PATH = PROJECT_ROOT / "warehouse" / "sample.duckdb"
    WAREHOUSE_URI = str(WAREHOUSE_PATH)
    SAMPLE_MODE = True


if os.environ.get("STATCAST_SAMPLE") == "1":
    use_sample_paths()
