from datetime import date

import pandas as pd

from statcast_pipeline.extract import partition_path
from statcast_pipeline.extract_games import extract_games_range, parse_schedule


def _game(pk, status="Final", officials=None):
    g = {
        "gamePk": pk, "gameType": "R", "officialDate": "2024-06-01", "gameDate": "2024-06-01T23:05:00Z",
        "status": {"detailedState": status},
        "teams": {"home": {"team": {"id": 143, "name": "Philadelphia Phillies"}},
                  "away": {"team": {"id": 121, "name": "New York Mets"}}},
        "venue": {"name": "Citizens Bank Park"}, "doubleHeader": "N", "gameNumber": 1,
    }
    if officials is not None:
        g["officials"] = officials
    return g


PLATE = [{"official": {"id": 1, "fullName": "Plate Ump"}, "officialType": "Home Plate"},
         {"official": {"id": 2, "fullName": "First Ump"}, "officialType": "First Base"}]


def test_parse_schedule_reads_games_and_inline_officials():
    games, officials = parse_schedule({"dates": [{"date": "2024-06-01", "games": [_game(10, officials=PLATE)]}]})
    assert games.loc[0, "home_team_name"] == "Philadelphia Phillies"
    assert games.loc[0, "venue_name"] == "Citizens Bank Park"
    assert set(officials["official_type"]) == {"Home Plate", "First Base"}


def test_falls_back_to_boxscore_for_final_games_without_officials():
    calls = []

    def boxscore(pk):
        calls.append(pk)
        return PLATE

    _, officials = parse_schedule({"dates": [{"games": [_game(10)]}]}, boxscore)
    assert calls == [10]
    assert (officials["official_type"] == "Home Plate").sum() == 1


def test_no_boxscore_call_for_unfinished_games():
    calls = []
    parse_schedule({"dates": [{"games": [_game(10, status="Postponed")]}]}, lambda pk: calls.append(pk) or [])
    assert calls == []


def test_malformed_official_entries_are_skipped():
    bad = [{"officialType": "Home Plate"}, {"official": {}, "officialType": "First Base"}]
    _, officials = parse_schedule({"dates": [{"games": [_game(10, officials=bad)]}]})
    assert officials.empty


def test_extract_games_range_writes_both_partitions_and_skips_existing(tmp_path):
    day = date(2024, 6, 1)
    payload = {"dates": [{"date": "2024-06-01", "games": [_game(10, officials=PLATE), _game(11, officials=PLATE)]}]}
    fetches = []

    def fetch(d):
        fetches.append(d)
        return payload

    kwargs = dict(fetch=fetch, fetch_officials=lambda pk: [], games_base=tmp_path / "g", officials_base=tmp_path / "o")
    stats = extract_games_range(day, day, **kwargs)

    assert stats["games"] == 2 and stats["games_with_plate_umpire"] == 2
    assert len(pd.read_parquet(partition_path(day, tmp_path / "g", "games.parquet"))) == 2
    assert len(pd.read_parquet(partition_path(day, tmp_path / "o", "officials.parquet"))) == 4

    extract_games_range(day, day, **kwargs)
    assert len(fetches) == 1  # second run skipped the existing day


def test_day_without_games_writes_nothing(tmp_path):
    day = date(2024, 12, 25)
    stats = extract_games_range(day, day, fetch=lambda d: {"dates": []}, fetch_officials=lambda pk: [],
                                games_base=tmp_path / "g", officials_base=tmp_path / "o")
    assert stats["days_written"] == 0
    assert not any(tmp_path.rglob("*.parquet"))


def test_fallback_covers_rain_shortened_and_tied_games():
    calls = []
    for status in ("Completed Early: Rain", "Final: Tied", "Suspended: Rain"):
        parse_schedule({"dates": [{"games": [_game(10, status=status)]}]}, lambda pk: calls.append(pk) or PLATE)
    assert calls == [10, 10, 10]


def test_fill_gaps_extracts_only_days_with_pitches_but_no_games(tmp_path):
    from statcast_pipeline.extract import write_partition
    from statcast_pipeline.extract_games import days_missing_games, fill_gaps
    from statcast_pipeline.sample import make_fake_day

    sc, g, o = tmp_path / "sc", tmp_path / "g", tmp_path / "o"
    d1, d2 = date(2024, 5, 30), date(2024, 5, 31)
    for d in (d1, d2):
        write_partition(make_fake_day(d, 1, 5), d, sc)
    extract_games_range(d1, d1, fetch=lambda d: {"dates": []}, fetch_officials=lambda pk: [],
                        games_base=g, officials_base=o)  # d1 had no games -> still "missing"

    assert days_missing_games(sc, g) == [d1, d2]

    fetched = []
    fill_gaps(statcast_base=sc, games_base=g, officials_base=o, fetch_officials=lambda pk: [],
              fetch=lambda d: fetched.append(d) or {"dates": [{"games": [_game(int(d.strftime("%d")),
                                                                                officials=PLATE)]}]})
    assert fetched == [d1, d2]
    assert days_missing_games(sc, g) == []
