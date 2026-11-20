"""Small helpers for writing to the Parquet lake safely."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


def write_parquet_atomic(df: pd.DataFrame, target: Path) -> Path:
    """Write df to target via a temp file + rename, so readers never see a
    half-written file and a crash mid-write leaves the old file intact."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, target)  # atomic on the same filesystem
    return target
