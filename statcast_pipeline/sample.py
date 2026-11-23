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


# A fixed cast, so pitchers have real arsenals across days and umpires work many games.
# (pitch type, mean mph, mean horizontal break ft, mean induced vertical break ft, movement sd ft)
_PITCH_PROFILES = {
    "FF": (94.5, -0.55, 1.35, 0.12), "SI": (93.5, -1.25, 0.70, 0.12), "FC": (89.0, 0.20, 0.75, 0.12),
    "SL": (85.5, 0.45, 0.15, 0.14), "ST": (82.5, 1.15, 0.05, 0.15), "CU": (79.5, 0.70, -0.85, 0.15),
    "CH": (85.5, -1.20, 0.55, 0.13), "FS": (86.5, -0.85, 0.20, 0.14), "KN": (76.0, 0.00, 0.10, 0.55),
}
_ARSENALS = [["FF", "SL", "CH"], ["SI", "SL", "CH", "FF"], ["FF", "CU", "CH"], ["FF", "FC", "ST", "SI"],
             ["SI", "ST", "CH"], ["FF", "SL", "CU", "FS"], ["FF", "FS", "SL"], ["SI", "FC", "CU", "CH", "FF"]]


def _pitchers() -> list[dict]:
    rng = np.random.default_rng(42)
    staff = []
    for i in range(80):
        arsenal = ["KN", "FF"] if i == 79 else _ARSENALS[i % len(_ARSENALS)]
        weights = rng.dirichlet(np.ones(len(arsenal)) * 2.5)
        staff.append({"id": 500000 + i, "name": f"Pitcher{i:02d}, Sample", "hand": "L" if i % 4 == 0 else "R",
                      "arsenal": arsenal, "weights": weights,
                      "velo_shift": float(rng.normal(0, 1.5))})
    return staff


_PITCHERS = _pitchers()
_BATTERS = list(range(600000, 600400))
_PAD = (8.5 + 1.45) / 12          # half-width of the zone incl. ball radius, feet


def _called_strike_prob(plate_x, plate_z, sz_top, sz_bot, balls, strikes) -> float:
    """Umpire model: a soft edge around the rulebook zone that shrinks with two
    strikes and widens in hitter's counts, like the real effect."""
    edge = min(_PAD - abs(plate_x), plate_z - (sz_bot - 0.12), (sz_top + 0.12) - plate_z) * 12  # inches
    shift = -1.2 * (strikes == 2) + 0.8 * (balls == 3) + 0.4 * (balls - strikes > 1)
    return float(1 / (1 + np.exp(-(edge + shift) / 0.9)))


def make_fake_day(day: date, n_games: int = 3, pitches_per_game: int = 280, seed: int | None = None) -> pd.DataFrame:
    """Return a DataFrame shaped like one day of pybaseball.statcast() output."""
    rng = np.random.default_rng(seed if seed is not None else day.toordinal())
    rows = []
    for g in range(n_games):
        game_pk = 700000 + day.toordinal() % 100000 * 10 + g
        home, away = rng.choice(TEAMS, size=2, replace=False)
        game_pitchers = [_PITCHERS[j] for j in rng.choice(len(_PITCHERS), size=4, replace=False)]
        at_bat, pitch_no, balls, strikes = 1, 1, 0, 0
        batter = int(rng.choice(_BATTERS))
        for n in range(pitches_per_game):
            pitcher = game_pitchers[min(n * 4 // pitches_per_game, 3)]
            ptype = str(rng.choice(pitcher["arsenal"], p=pitcher["weights"]))
            mph, hb, ivb, sd = _PITCH_PROFILES[ptype]
            sz_top, sz_bot = round(float(rng.normal(3.4, 0.12)), 2), round(float(rng.normal(1.6, 0.08)), 2)
            plate_x = round(float(rng.normal(0.05, 0.75)), 2)
            plate_z = round(float(rng.normal(2.35, 0.75)), 2)
            in_zone = abs(plate_x) <= _PAD and sz_bot - 0.12 <= plate_z <= sz_top + 0.12
            swing_p = (0.68 if in_zone else 0.28) + (0.15 if strikes == 2 else 0)
            if rng.random() < swing_p:
                desc = str(rng.choice(["swinging_strike", "foul", "hit_into_play"], p=[0.22, 0.42, 0.36]))
            else:
                desc = "called_strike" if rng.random() < _called_strike_prob(
                    plate_x, plate_z, sz_top, sz_bot, balls, strikes) else "ball"
            in_play = desc == "hit_into_play"
            rows.append({
                "pitch_type": ptype,
                "game_date": pd.Timestamp(day),
                "release_speed": round(float(rng.normal(mph + pitcher["velo_shift"], 1.0)), 1),
                "release_pos_x": round(float(rng.normal(-1.5 if pitcher["hand"] == "R" else 1.5, 0.3)), 2),
                "release_pos_z": round(float(rng.normal(5.8, 0.2)), 2),
                "player_name": pitcher["name"],
                "batter": batter,
                "pitcher": pitcher["id"],
                "events": str(rng.choice(["single", "field_out", "double", "home_run"],
                                         p=[0.25, 0.6, 0.1, 0.05])) if in_play else None,
                "description": desc,
                "zone": int(rng.integers(1, 15)),
                "game_type": "R",
                "stand": str(rng.choice(["L", "R"])),
                "p_throws": pitcher["hand"],
                "home_team": home,
                "away_team": away,
                "type": DESCRIPTIONS[desc],
                "bb_type": str(rng.choice(["ground_ball", "line_drive", "fly_ball"])) if in_play else None,
                "balls": balls,
                "strikes": strikes,
                "game_year": day.year,
                "pfx_x": round(float(rng.normal(hb, sd)), 2),
                "pfx_z": round(float(rng.normal(ivb, sd)), 2),
                "plate_x": plate_x,
                "plate_z": plate_z,
                "outs_when_up": int(rng.integers(0, 3)),
                "inning": min(n * 9 // pitches_per_game + 1, 9),
                "inning_topbot": str(rng.choice(["Top", "Bot"])),
                "sz_top": sz_top,
                "sz_bot": sz_bot,
                "hit_distance_sc": float(rng.integers(5, 420)) if in_play else np.nan,
                "launch_speed": round(float(rng.normal(89, 12)), 1) if in_play else np.nan,
                "launch_angle": float(rng.integers(-30, 60)) if in_play else np.nan,
                "effective_speed": round(float(rng.normal(mph, 1.2)), 1),
                "release_spin_rate": float(rng.integers(1500, 2800)),
                "release_extension": round(float(rng.normal(6.3, 0.3)), 1),
                "game_pk": game_pk,
                "fielder_2": 650000 + g,
                "at_bat_number": at_bat,
                "pitch_number": pitch_no,
                "pitch_name": PITCH_TYPES[ptype],
                "spin_axis": float(rng.integers(0, 360)),
                "estimated_woba_using_speedangle": round(float(rng.uniform(0, 1.5)), 3) if in_play else np.nan,
                "delta_run_exp": round(float(rng.normal(0, 0.08)), 3),
                "bat_speed": round(float(rng.normal(71, 4)), 1) if desc in SWINGS else np.nan,
            })
            # Advance the count / at-bat in a simple, roughly realistic way.
            ends_pa = in_play or (desc == "ball" and balls == 3) or (
                desc in {"called_strike", "swinging_strike"} and strikes == 2)
            if ends_pa:
                at_bat, pitch_no, balls, strikes = at_bat + 1, 1, 0, 0
                batter = int(rng.choice(_BATTERS))
            else:
                pitch_no += 1
                if desc == "ball":
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
        ump_id, ump_name = UMPIRES[(row.game_pk // 10 * 3 + row.game_pk % 10) % len(UMPIRES)]
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
