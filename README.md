# Statcast Pipeline

An ELT pipeline for MLB pitch-level data: **Baseball Savant + MLB Stats API → Parquet data lake → DuckDB warehouse → dbt models**, with tests, Docker and CI. Built as a data-engineering portfolio project.

```
 Baseball Savant ─(pybaseball, 1 day/request)─▶ data/raw/statcast/dt=…/pitches.parquet ─┐
 MLB Stats API ──(schedule + umpires)────────▶ data/raw/games/…, data/raw/game_officials/… ─┤  load.py
 Chadwick register (pybaseball) ─────────────▶ data/raw/players/players.parquet ───────────┘    │
                                                                                                ▼
                                                         DuckDB  raw.*  ──dbt build──▶  staging ▶ intermediate ▶ core ▶ analytics
```

**Status:** Weeks 1–2 of 4 complete (extract, load, full dbt model layer, backfill, tests, Docker, CI).

## Quickstart

Requires Python 3.10–3.12.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Offline demo with generated data (no network). Note: sample values are random,
# so the umpire accuracy numbers it produces are meaningless.
python -m statcast_pipeline.run --sample --start 2024-06-01 --end 2024-06-07

# Real data: one week
python -m statcast_pipeline.run --start 2024-06-01 --end 2024-06-07

# Real data: whole seasons (resumable; roughly 1–1.5 hours per season)
python -m statcast_pipeline.backfill --seasons 2023 2024 2025
```

Individual steps:

```bash
python -m statcast_pipeline.extract --start 2024-06-01 --end 2024-06-07        # pitches
python -m statcast_pipeline.extract_games --start 2024-06-01 --end 2024-06-07  # games + umpires
python -m statcast_pipeline.extract_players                                    # names (weekly)
python -m statcast_pipeline.load
dbt build --project-dir dbt --profiles-dir dbt                                 # add --full-refresh to rebuild
```

Docker:

```bash
docker compose build
docker compose run --rm pipeline --start 2024-06-01 --end 2024-06-07
```

## Data model

| Layer | Model | Grain | What it's for |
| --- | --- | --- | --- |
| staging | `stg_pitches`, `stg_games`, `stg_game_officials`, `stg_players` | one row per source record | Typed, renamed, deduplicated sources |
| intermediate | `int_called_pitches` | pitch (takes only) | Each called pitch scored against the rulebook zone, with the plate umpire |
| core | `fct_pitches` (incremental) | pitch | Central fact table with swing / whiff / zone flags |
| core | `dim_games` | game | Teams, venue, home-plate umpire |
| core | `dim_players` | player | Names and FanGraphs / Baseball-Reference IDs |
| analytics | `mart_pitcher_arsenal` | pitcher × season × pitch type | Usage, velocity, movement, whiff %, CSW %, run value per 100 |
| analytics | `mart_umpire_accuracy` | umpire × season | Accuracy vs. league, missed strikes/balls, edge and 2-strike / 3-ball accuracy |
| analytics | `mart_called_accuracy_by_count` | season × count | Where umpires miss, by ball-strike count |
| analytics | `mart_pitch_movement_consistency` | season × pitch type | Within-pitcher movement spread (knuckleballs stand out) |

### Example questions

```sql
-- Most accurate umpires in 2024 (min 2,000 called pitches)
select umpire_name, called_pitches, round(accuracy, 4) as accuracy, round(accuracy_vs_league, 4) as vs_league
from analytics.mart_umpire_accuracy
where season = 2024 and called_pitches >= 2000
order by accuracy desc limit 10;

-- Do umpires shrink the zone with two strikes?
select count_state, called_pitches, round(in_zone_called_ball_rate, 3) as strikes_called_balls
from analytics.mart_called_accuracy_by_count where season = 2024 order by balls, strikes;

-- Zack Wheeler's 2024 arsenal
select pitch_name, round(usage_rate, 3) as usage, avg_velocity_mph, round(whiff_rate, 3) as whiff, run_value_per_100
from analytics.mart_pitcher_arsenal where pitcher_name = 'Zack Wheeler' and season = 2024 order by pitches desc;
```

Run them with `duckdb warehouse/statcast.duckdb` or from Python with `duckdb.connect(...)`.

## Design decisions

| Decision | Why |
| --- | --- |
| One game day per request | Baseball Savant caps rows per query; day-sized pulls avoid silent truncation |
| Idempotent writes (temp file + atomic rename, one file per day) | Retries and re-runs never duplicate data |
| Skip existing days unless `--force` | Multi-season backfills resume after a failure |
| Retries with exponential backoff; 1-second pause during backfills | The sources are public endpoints that time out occasionally; be polite |
| Umpires from `schedule?hydrate=officials`, falling back to each game's boxscore | One request per day normally, with no gaps; the log reports coverage per day |
| Parquet lake + DuckDB `union_by_name` | Savant adds columns over the years; matching by name handles schema drift |
| Incremental `fct_pitches` keyed on `extracted_at` (not game date), plus a 3-day lookback | Picks up both new days *and* backfilled older seasons; the lookback catches late corrections. `delete+insert` on `pitch_id` makes re-processing safe |
| Strike zone padded by the ball's radius (1.45 in), defined once in a macro | The rule is "any part of the ball touches the zone"; one macro keeps every model consistent |
| Spring training and exhibitions excluded from analytics marts | Different rosters and umpires; would distort season stats |

## Data quality checks (59 in total)

- Keys: `unique` + `not_null` on every model's grain; `relationships` from `fct_pitches` to `dim_games` and `dim_players`
- Domain values: balls 0–3, strikes 0–2, result codes, pitch types (warn), name sources, miss types
- Singular tests: release speed 30–110 mph; every rate in the marts between 0 and 1; the by-count miss rates reconcile with overall accuracy; strike-zone macro probe cases
- Coverage (warn): game days with under 100 pitches; more than 5% of games without a home-plate umpire
- `dbt source freshness` warns after 2 days without new data (expected in the off-season)

## Troubleshooting: games without a home-plate umpire

If `assert_plate_umpire_coverage` or `not_null_int_called_pitches_umpire_id` warns:

```bash
# 1. Fetch games/umpires for any day that has pitches but no games data yet
python -m statcast_pipeline.extract_games --fill-gaps
# 2. Re-pull days whose games came back without umpires (uses the boxscore fallback)
python -m statcast_pipeline.extract_games --start 2024-06-01 --end 2024-06-07 --force
# 3. Reload and rebuild
python -m statcast_pipeline.load && dbt build --project-dir dbt --profiles-dir dbt
```

To see which games are affected:

```sql
select game_date, game_pk, home_team, away_team, has_schedule_data, game_status
from core.dim_games where home_plate_umpire_id is null order by game_date;
```

`has_schedule_data = false` means the games extract never ran for that date; `true` means the API returned the game without umpires.

## Project layout

```
statcast_pipeline/
  extract.py           Savant -> date-partitioned Parquet
  extract_games.py     MLB Stats API schedule + umpires -> Parquet
  extract_players.py   Chadwick player register -> Parquet (weekly)
  load.py              Parquet -> DuckDB raw.* tables
  run.py               extract -> load -> dbt build (what Docker runs)
  backfill.py          whole seasons, resumable
  sample.py            fake data in the same shapes, for tests and CI
  storage.py, config.py
dbt/
  macros/              strike-zone geometry, schema naming
  models/staging/      one view per source
  models/intermediate/ int_called_pitches
  models/marts/core/   fct_pitches, dim_games, dim_players
  models/marts/analytics/  four analysis marts
  tests/               singular data tests
tests/                 pytest unit tests (21)
```

## Roadmap

- [x] **Week 1:** extract, load, `stg_pitches`, tests, Docker, CI
- [x] **Week 2:** umpires and players; intermediate, core and analytics models; incremental fact table; season backfill
- [ ] **Week 3:** Airflow DAGs (daily + backfill) with retries and alerts; MotherDuck as the prod target
- [ ] **Week 4:** Streamlit dashboard; dbt docs on GitHub Pages

**Off-season note:** MLB has no games from November to late February, so the daily job finds nothing new; it's demoed by replaying historical dates.

## Data sources

Pitch data from [Baseball Savant](https://baseballsavant.mlb.com/) via [pybaseball](https://github.com/jldbc/pybaseball); schedules and umpires from the MLB Stats API; player IDs from the [Chadwick Bureau register](https://github.com/chadwickbureau/register). MLB data is used here for non-commercial, educational purposes and is not committed to this repo.
