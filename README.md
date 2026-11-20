# Statcast Pipeline

An ELT pipeline for MLB pitch-level data: **Baseball Savant → Parquet data lake → DuckDB warehouse → dbt models**, with tests, Docker and CI. Built as a data-engineering portfolio project.

```
 Baseball Savant ──(pybaseball, 1 day per request, retries)──▶ data/raw/statcast/dt=YYYY-MM-DD/pitches.parquet
                                                                             │
                                                     load.py (union_by_name) ▼
                                                              DuckDB: raw.pitches
                                                                             │
                                                         dbt build (models + tests)
                                                                             ▼
                                                      staging.stg_pitches ─▶ (Week 2: facts, dims, marts)
```

**Status:** Week 1 of 4 — extract, load, first staging model, tests, Docker, CI.

## Quickstart (local Python)

Requires Python 3.10–3.12.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. Try it offline first with generated data (no network needed)
python -m statcast_pipeline.run --sample --start 2024-06-01 --end 2024-06-07

# 2. Then pull one real week of 2024 games
python -m statcast_pipeline.run --start 2024-06-01 --end 2024-06-07
```

Each step can also run on its own:

```bash
python -m statcast_pipeline.extract --start 2024-06-01 --end 2024-06-07   # add --force to re-pull
python -m statcast_pipeline.load
dbt build --project-dir dbt --profiles-dir dbt
```

## Quickstart (Docker)

```bash
docker compose build
docker compose run --rm pipeline --start 2024-06-01 --end 2024-06-07
```

`data/` and `warehouse/` are mounted from your machine, so results persist between runs.

## Explore the data

```bash
python -c "import duckdb; print(duckdb.connect('warehouse/statcast.duckdb').sql('''
  select pitch_name, count(*) as pitches, round(avg(release_speed_mph), 1) as avg_mph,
         round(avg(spin_rate_rpm)) as avg_spin
  from staging.stg_pitches group by 1 order by 2 desc
'''))"
```

Or open the file in the DuckDB CLI (`duckdb warehouse/statcast.duckdb`) or DBeaver.

## Design decisions

| Decision | Why |
| --- | --- |
| One game day per request | Baseball Savant caps rows per query; day-sized pulls avoid silent truncation |
| Idempotent writes (temp file + atomic rename, one file per day) | Retries and re-runs never duplicate data |
| Skip existing days unless `--force` | Multi-season backfills can resume after a failure |
| Retries with exponential backoff (tenacity) | The source is a scraped endpoint that times out occasionally |
| Parquet lake + DuckDB `union_by_name` | Savant adds columns over the years (e.g., bat tracking in 2024); matching by name handles schema drift |
| Explicit casts and renames in `stg_pitches` | One place where raw quirks are fixed; everything downstream gets clean types |
| Dedupe on `game_pk, at_bat_number, pitch_number` | Defines the grain (one row per pitch) and enforces it with a `unique` test |
| `--sample` mode | Tests and CI run offline and fast without hitting Savant |

## Data quality checks

- `unique` + `not_null` on `pitch_id`; `not_null` on game, date, pitcher, batter
- Accepted values for balls (0–3), strikes (0–2) and result code (B/S/X); pitch type warns on new codes
- Singular tests: release speed between 30 and 110 mph; warn if a game day has fewer than 100 pitches (likely a truncated download)
- `dbt source freshness` warns when no new data has arrived in 2 days (expected in the off-season)

## Project layout

```
statcast_pipeline/
  extract.py      Savant -> date-partitioned Parquet
  load.py         Parquet -> DuckDB raw.pitches
  run.py          extract -> load -> dbt build (what Docker runs)
  sample.py       fake Statcast-shaped data for tests and CI
  config.py       paths (overridable with DATA_DIR, WAREHOUSE_PATH)
dbt/
  models/staging/ sources, stg_pitches, column tests
  tests/          singular data tests
tests/            pytest unit tests
.github/workflows/ci.yml   lint + tests + sample pipeline on every push
```

## Roadmap

- [x] **Week 1:** extract, load, `stg_pitches`, tests, Docker, CI
- [ ] **Week 2:** umpire data from MLB-StatsAPI; `int_called_pitches`; incremental `fct_pitches`; `dim_players`, `dim_games`; marts for pitcher arsenals and umpire accuracy; 2015–2026 backfill
- [ ] **Week 3:** Airflow DAGs (daily + backfill) with retries and alerts; MotherDuck as the prod target
- [ ] **Week 4:** Streamlit dashboard; dbt docs on GitHub Pages

**Off-season note:** MLB has no games from November to late February, so the daily job finds nothing new. It's demoed by replaying historical dates.

## Data source

Pitch data comes from [Baseball Savant](https://baseballsavant.mlb.com/) via [pybaseball](https://github.com/jldbc/pybaseball). It is MLB's data, used here for non-commercial, educational purposes; raw data is not committed to this repo.
"# Statcast-Dashboard" 
"# Statcast-Dashboard" 
"# Statcast-Dashboard" 
