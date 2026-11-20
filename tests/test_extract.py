from datetime import date

import pandas as pd
import pytest

from statcast_pipeline.extract import daterange, extract_range, partition_path, write_partition
from statcast_pipeline.sample import make_fake_day

DAY = date(2024, 6, 1)


def test_daterange_is_inclusive():
    days = list(daterange(date(2024, 6, 1), date(2024, 6, 3)))
    assert days == [date(2024, 6, 1), date(2024, 6, 2), date(2024, 6, 3)]


def test_daterange_rejects_reversed_range():
    with pytest.raises(ValueError):
        list(daterange(date(2024, 6, 3), date(2024, 6, 1)))


def test_partition_path_uses_hive_style_folder(tmp_path):
    assert partition_path(DAY, tmp_path) == tmp_path / "dt=2024-06-01" / "pitches.parquet"


def test_write_partition_adds_metadata(tmp_path):
    path = write_partition(make_fake_day(DAY, n_games=1, pitches_per_game=10), DAY, tmp_path)
    written = pd.read_parquet(path)
    assert len(written) == 10
    assert {"_extracted_at", "_source"} <= set(written.columns)


def test_rewriting_a_day_replaces_it_instead_of_duplicating(tmp_path):
    write_partition(make_fake_day(DAY, n_games=1, pitches_per_game=10), DAY, tmp_path)
    write_partition(make_fake_day(DAY, n_games=1, pitches_per_game=4), DAY, tmp_path)

    files = list(tmp_path.rglob("*.parquet"))
    assert len(files) == 1
    assert len(pd.read_parquet(files[0])) == 4
    assert not list(tmp_path.rglob("*.tmp")), "temp file should be renamed away"


def test_empty_day_writes_nothing_and_removes_stale_file(tmp_path):
    write_partition(make_fake_day(DAY, n_games=1, pitches_per_game=5), DAY, tmp_path)
    assert write_partition(pd.DataFrame(), DAY, tmp_path) is None
    assert not partition_path(DAY, tmp_path).exists()


def test_extract_range_skips_existing_days_unless_forced(tmp_path):
    calls = []

    def fake_fetch(day):
        calls.append(day)
        return make_fake_day(day, n_games=1, pitches_per_game=5)

    start, end = date(2024, 6, 1), date(2024, 6, 3)

    first = extract_range(start, end, fetch=fake_fetch, base=tmp_path)
    assert first["written"] == 3 and len(calls) == 3

    second = extract_range(start, end, fetch=fake_fetch, base=tmp_path)
    assert second["skipped_existing"] == 3 and len(calls) == 3  # resumable backfill

    extract_range(start, end, force=True, fetch=fake_fetch, base=tmp_path)
    assert len(calls) == 6


def test_extract_range_counts_days_without_games(tmp_path):
    stats = extract_range(DAY, DAY, fetch=lambda d: pd.DataFrame(), base=tmp_path)
    assert stats["no_games"] == 1 and stats["written"] == 0
