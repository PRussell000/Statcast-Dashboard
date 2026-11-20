"""Central configuration. Paths can be overridden with environment variables,
which is how Docker and (later) Airflow point the pipeline at mounted volumes."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
RAW_STATCAST_DIR = DATA_DIR / "raw" / "statcast"
RAW_GAMES_DIR = DATA_DIR / "raw" / "games"
RAW_OFFICIALS_DIR = DATA_DIR / "raw" / "game_officials"
RAW_PLAYERS_PATH = DATA_DIR / "raw" / "players" / "players.parquet"

WAREHOUSE_PATH = Path(
    os.environ.get("WAREHOUSE_PATH", PROJECT_ROOT / "warehouse" / "statcast.duckdb")
)

DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"

# Name of the Parquet file written inside each date partition.
PARTITION_FILENAME = "pitches.parquet"
GAMES_FILENAME = "games.parquet"
OFFICIALS_FILENAME = "officials.parquet"

MLB_STATSAPI_BASE = "https://statsapi.mlb.com/api/v1"

# Seconds to wait between days during long backfills, to be polite to the sources.
DEFAULT_PAUSE_SECONDS = float(os.environ.get("PAUSE_SECONDS", "1.0"))
