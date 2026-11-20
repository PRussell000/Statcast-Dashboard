from datetime import date

import duckdb
import pytest

from statcast_pipeline.extract import write_partition
from statcast_pipeline.load import load_raw_pitches
from statcast_pipeline.sample import make_fake_day


def test_load_builds_raw_table_with_partition_column(tmp_path):
    raw, wh = tmp_path / "raw", tmp_path / "wh.duckdb"
    for d in (date(2024, 6, 1), date(2024, 6, 2)):
        write_partition(make_fake_day(d, n_games=1, pitches_per_game=10), d, raw)

    assert load_raw_pitches(raw, wh) == 20

    with duckdb.connect(str(wh)) as con:
        days = con.execute("select count(distinct dt) from raw.pitches").fetchone()[0]
    assert days == 2


def test_load_handles_schema_drift_between_seasons(tmp_path):
    """Older seasons lack newer columns such as bat_speed; union_by_name must cope."""
    raw, wh = tmp_path / "raw", tmp_path / "wh.duckdb"
    old_day, new_day = date(2019, 6, 1), date(2024, 6, 1)
    write_partition(make_fake_day(old_day, 1, 10).drop(columns=["bat_speed"]), old_day, raw)
    write_partition(make_fake_day(new_day, 1, 10), new_day, raw)

    load_raw_pitches(raw, wh)

    with duckdb.connect(str(wh)) as con:
        nulls_2019 = con.execute(
            "select count(*) from raw.pitches where game_year = 2019 and bat_speed is null"
        ).fetchone()[0]
    assert nulls_2019 == 10


def test_load_fails_clearly_when_nothing_extracted(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_raw_pitches(tmp_path / "empty", tmp_path / "wh.duckdb")
