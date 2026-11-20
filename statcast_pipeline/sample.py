"""Generate fake Statcast-shaped data so the pipeline, tests and CI run without
network access. Column names and types mirror what pybaseball returns; the
values are random but plausible.

Usage:
    python -m statcast_pipeline.run --sample --start 2024-06-01 --end 2024-06-03
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

PITCH_TYPES = {
    "FF": "4-Seam Fastball", "SI": "Sinker", "FC": "Cutter", "SL": "Slider",
    "ST": "Sweeper", "CU": "Curveball", "CH": "Changeup", "FS": "Split-Finger",
    "KN": "Knuckleball",
}
DESCRIPTIONS = {
    "ball": "B", "called_strike": "S", "swinging_strike": "S",
    "foul": "S", "hit_into_play": "X", "blocked_ball": "B",
}
SWINGS = {"foul", "hit_into_play", "swinging_strike"}
TEAMS = ["PHI", "NYM", "ATL", "MIA", "WSH", "LAD", "SD", "NYY", "BOS", "HOU"]


def make_fake_day(day: date, n_games: int = 3, pitches_per_game: int = 280, seed: int | None = None) -> pd.DataFrame:
    """Return a DataFrame shaped like one day of pybaseball.statcast() output."""
    rng = np.random.default_rng(seed if seed is not None else day.toordinal())
    rows = []
    for g in range(n_games):
        game_pk = 700000 + day.toordinal() % 100000 * 10 + g
        home, away = rng.choice(TEAMS, size=2, replace=False)
        at_bat, pitch_no, balls, strikes = 1, 1, 0, 0
        for _ in range(pitches_per_game):
            desc = rng.choice(list(DESCRIPTIONS), p=[0.33, 0.17, 0.11, 0.18, 0.18, 0.03])
            ptype = rng.choice(list(PITCH_TYPES))
            in_play = desc == "hit_into_play"
            rows.append({
                "pitch_type": ptype,
                "game_date": pd.Timestamp(day),
                "release_speed": round(float(rng.normal(65 if ptype == "KN" else 89, 4)), 1),
                "release_pos_x": round(float(rng.normal(-1.5, 0.8)), 2),
                "release_pos_z": round(float(rng.normal(5.8, 0.3)), 2),
                "player_name": f"Pitcher, {rng.integers(1, 40)}",
                "batter": int(rng.integers(600000, 700000)),
                "pitcher": int(rng.integers(500000, 600000)),
                "events": rng.choice(["single", "field_out", "double", "home_run"]) if in_play else None,
                "description": desc,
                "zone": int(rng.integers(1, 15)),
                "game_type": "R",
                "stand": rng.choice(["L", "R"]),
                "p_throws": rng.choice(["L", "R"]),
                "home_team": home,
                "away_team": away,
                "type": DESCRIPTIONS[desc],
                "bb_type": rng.choice(["ground_ball", "line_drive", "fly_ball"]) if in_play else None,
                "balls": balls,
                "strikes": strikes,
                "game_year": day.year,
                "pfx_x": round(float(rng.normal(0, 0.8)), 2),
                "pfx_z": round(float(rng.normal(1, 0.6)), 2),
                "plate_x": round(float(rng.normal(0, 0.9)), 2),
                "plate_z": round(float(rng.normal(2.4, 0.9)), 2),
                "outs_when_up": int(rng.integers(0, 3)),
                "inning": int(rng.integers(1, 10)),
                "inning_topbot": rng.choice(["Top", "Bot"]),
                "sz_top": round(float(rng.normal(3.4, 0.1)), 2),
                "sz_bot": round(float(rng.normal(1.6, 0.1)), 2),
                "hit_distance_sc": float(rng.integers(5, 420)) if in_play else np.nan,
                "launch_speed": round(float(rng.normal(89, 12)), 1) if in_play else np.nan,
                "launch_angle": float(rng.integers(-30, 60)) if in_play else np.nan,
                "effective_speed": round(float(rng.normal(89, 4)), 1),
                "release_spin_rate": float(rng.integers(1500, 2800)),
                "release_extension": round(float(rng.normal(6.3, 0.3)), 1),
                "game_pk": game_pk,
                "fielder_2": int(rng.integers(500000, 700000)),
                "at_bat_number": at_bat,
                "pitch_number": pitch_no,
                "pitch_name": PITCH_TYPES[ptype],
                "spin_axis": float(rng.integers(0, 360)),
                "estimated_woba_using_speedangle": round(float(rng.uniform(0, 1.5)), 3) if in_play else np.nan,
                "delta_run_exp": round(float(rng.normal(0, 0.08)), 3),
                "bat_speed": round(float(rng.normal(71, 4)), 1) if desc in SWINGS else np.nan,
            })
            # Advance the count / at-bat in a simple, roughly realistic way.
            ends_pa = in_play or (desc in {"ball", "blocked_ball"} and balls == 3) or (
                desc in {"called_strike", "swinging_strike"} and strikes == 2)
            if ends_pa:
                at_bat, pitch_no, balls, strikes = at_bat + 1, 1, 0, 0
            else:
                pitch_no += 1
                if desc in {"ball", "blocked_ball"}:
                    balls += 1
                elif desc != "foul" or strikes < 2:
                    strikes = min(strikes + 1, 2)
    return pd.DataFrame(rows)


def fake_fetch(day: date) -> pd.DataFrame:
    """Drop-in replacement for extract.fetch_day. Mondays have no games, so the
    'no games' path gets exercised too."""
    if day.weekday() == 0:
        return pd.DataFrame()
    return make_fake_day(day)


# --- Games, umpires and players (Week 2) -------------------------------------

UMPIRES = [(427000 + i, name) for i, name in enumerate(
    ["Ump Alvarez", "Ump Baker", "Ump Chen", "Ump Diaz", "Ump Evans",
     "Ump Foster", "Ump Garcia", "Ump Hughes", "Ump Ito", "Ump Jones"])]
_BOXSCORE_ONLY: dict[int, list[dict]] = {}


def fake_fetch_schedule(day: date) -> dict:
    """A schedule payload in the MLB Stats API shape, matching make_fake_day's
    games. The last game of each day omits umpires, which forces the boxscore
    fallback path."""
    if day.weekday() == 0:
        return {"dates": []}
    pitches = make_fake_day(day)
    games = pitches.drop_duplicates("game_pk")[["game_pk", "home_team", "away_team"]]
    out = []
    for i, row in enumerate(games.itertuples(index=False)):
        ump_id, ump_name = UMPIRES[row.game_pk % len(UMPIRES)]
        officials = [
            {"official": {"id": ump_id, "fullName": ump_name}, "officialType": "Home Plate"},
            {"official": {"id": ump_id + 100, "fullName": f"{ump_name} Jr."}, "officialType": "First Base"},
        ]
        game = {
            "gamePk": int(row.game_pk), "gameType": "R", "officialDate": day.isoformat(),
            "gameDate": f"{day.isoformat()}T23:05:00Z", "status": {"detailedState": "Final"},
            "teams": {"home": {"team": {"id": 100 + TEAMS.index(row.home_team), "name": row.home_team}},
                      "away": {"team": {"id": 100 + TEAMS.index(row.away_team), "name": row.away_team}}},
            "venue": {"name": f"{row.home_team} Park"}, "doubleHeader": "N", "gameNumber": 1,
        }
        if i == len(games) - 1:
            _BOXSCORE_ONLY[int(row.game_pk)] = officials
        else:
            game["officials"] = officials
        out.append(game)
    return {"dates": [{"date": day.isoformat(), "games": out}]}


def fake_fetch_boxscore_officials(game_pk: int) -> list[dict]:
    return _BOXSCORE_ONLY.get(int(game_pk), [])


def fake_players_from_lake(statcast_dir) -> pd.DataFrame:
    """A Chadwick-register-shaped table for every pitcher and batter in the
    sample partitions (a few left out on purpose, to exercise the name fallback)."""
    files = list(statcast_dir.glob("dt=*/*.parquet"))
    ids: set[int] = set()
    for f in files:
        df = pd.read_parquet(f, columns=["pitcher", "batter"])
        ids |= set(df["pitcher"].astype(int)) | set(df["batter"].astype(int))
    ids_sorted = sorted(ids)[: int(len(ids) * 0.95)]
    return pd.DataFrame({
        "name_last": [f"Last{i}" for i in ids_sorted],
        "name_first": [f"First{i}" for i in ids_sorted],
        "key_mlbam": ids_sorted,
        "key_retro": None, "key_bbref": None,
        "key_fangraphs": [-1] * len(ids_sorted),
        "mlb_played_first": 2015.0, "mlb_played_last": 2024.0,
    })
