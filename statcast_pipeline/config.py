"""Central configuration. Paths can be overridden with environment variables,
which is how Docker and (later) Airflow point the pipeline at mounted volumes."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))
RAW_STATCAST_DIR = DATA_DIR / "raw" / "statcast"

WAREHOUSE_PATH = Path(
    os.environ.get("WAREHOUSE_PATH", PROJECT_ROOT / "warehouse" / "statcast.duckdb")
)

DBT_PROJECT_DIR = PROJECT_ROOT / "dbt"

# Name of the Parquet file written inside each date partition.
PARTITION_FILENAME = "pitches.parquet"
