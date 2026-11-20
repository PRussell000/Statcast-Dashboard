import os
import time
from datetime import date

import duckdb
import pandas as pd

from statcast_pipeline.backfill import season_window
from statcast_pipeline.extract import write_partition
from statcast_pipeline.extract_players import extract_players
from statcast_pipeline.load import load_all
from statcast_pipeline.sample import make_fake_day


def _register():
    return pd.DataFrame({
        "name_last": ["Wheeler", "Unknown"], "name_first": ["Zack", "Prospect"],
        "key_mlbam": [554430, -1], "key_retro": [None, None], "key_bbref": ["wheelza01", None],
        "key_fangraphs": [10310, -1], "mlb_played_first": [2013.0, None], "mlb_played_last": [2024.0, None],
    })


def test_players_drops_rows_without_mlbam_id(tmp_path):
    target = tmp_path / "players.parquet"
    assert extract_players(force=True, fetch=_register, target=target) == 1
    assert pd.read_parquet(target)["key_mlbam"].tolist() == [554430]


def test_players_skips_fresh_file_and_refreshes_stale_one(tmp_path):
    target = tmp_path / "players.parquet"
    extract_players(force=True, fetch=_register, target=target)
    assert extract_players(fetch=_register, target=target) is None          # fresh: skipped

    eight_days_ago = time.time() - 8 * 24 * 3600
    os.utime(target, (eight_days_ago, eight_days_ago))
    assert extract_players(fetch=_register, target=target) == 1             # stale: refreshed


def test_load_all_creates_empty_optional_tables(tmp_path):
    data_dir, wh = tmp_path / "data", tmp_path / "wh.duckdb"
    day = date(2024, 6, 1)
    write_partition(make_fake_day(day, 1, 10), day, data_dir / "raw" / "statcast")

    counts = load_all(data_dir, wh)

    assert counts == {"pitches": 10, "games": 0, "game_officials": 0, "players": 0}
    with duckdb.connect(str(wh)) as con:
        cols = {r[0] for r in con.execute("describe raw.game_officials").fetchall()}
    assert {"game_pk", "official_id", "official_type"} <= cols


def test_season_window_covers_spring_through_postseason():
    start, end = season_window(2024)
    assert start == date(2024, 3, 15) and end == date(2024, 11, 10)
