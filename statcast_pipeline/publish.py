
"""Publish step: export the small analytics tables the dashboard needs.

The warehouse holds millions of rows and never leaves your machine. This step
writes compact, aggregated Parquet files plus a health.json summary to
dashboard/data/ (a few MB in total). Those files are committed to the repo, so
the Streamlit app runs anywhere - including Streamlit Community Cloud - with no
database connection or secrets.

Sample runs write to dashboard/data_sample/ instead (git-ignored), so demo data
can never be published by accident.

Usage:
    python -m statcast_pipeline.publish
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from statcast_pipeline import config

log = logging.getLogger(__name__)

EXPORTS = {
    "umpire_accuracy": "select * from analytics.mart_umpire_accuracy",
    "accuracy_by_count": "select * from analytics.mart_called_accuracy_by_count",
    "zone_grid": "select * from analytics.mart_called_zone_grid",
    # Drop tiny samples: a pitch thrown 3 times all season isn't an "arsenal" entry.
    "pitcher_arsenal": "select * from analytics.mart_pitcher_arsenal where pitches >= 25",
    "movement_consistency": "select * from analytics.mart_pitch_movement_consistency",
}


def output_dir() -> Path:
    name = "data_sample" if config.SAMPLE_MODE else "data"
    return config.PROJECT_ROOT / "dashboard" / name


def _dbt_results(run_results: Path) -> dict | None:
    """Summarize dbt's run_results.json: counts by status and the non-passing checks."""
    if not run_results.exists():
        return None
    data = json.loads(run_results.read_text())
    counts: dict[str, int] = {}
    flagged = []
    for r in data.get("results", []):
        status = r.get("status")
        counts[status] = counts.get(status, 0) + 1
        if status in {"warn", "error", "fail"}:
            flagged.append({"node": r.get("unique_id", "").split(".")[-1], "status": status,
                            "failures": r.get("failures")})
    return {
        "generated_at": data.get("metadata", {}).get("generated_at"),
        "elapsed_seconds": round(data.get("elapsed_time", 0), 1),
        "status_counts": counts,
        "flagged": flagged,
    }


def build_health(con: duckdb.DuckDBPyConnection) -> dict:
    rows = {
        t: con.execute(f"select count(*) from {t}").fetchone()[0]
        for t in ["raw.pitches", "raw.games", "raw.game_officials", "raw.players",
                  "core.fct_pitches", "core.dim_games", "core.dim_players"]
    }
    seasons = con.execute("""
        select
            g.season,
            count(*) filter (where g.game_type = 'R')                       as regular_season_games,
            count(*) filter (where g.game_type in ('F', 'D', 'L', 'W'))     as postseason_games,
            count(*) filter (where g.game_type = 'S')                       as spring_games,
            sum(g.pitches_tracked)                                          as pitches,
            min(g.game_date)::varchar                                       as first_game,
            max(g.game_date)::varchar                                       as last_game,
            count(*) filter (where g.game_type = 'R' and g.home_plate_umpire_id is null)
                                                                            as regular_games_without_umpire
        from core.dim_games g
        group by g.season
        order by g.season
    """).fetchdf().to_dict(orient="records")
    # From the raw table, where _extracted_at is still time-zone aware: report it in UTC.
    last_load = con.execute(
        "select strftime(max(_extracted_at) at time zone 'UTC', '%Y-%m-%d %H:%M') from raw.pitches"
    ).fetchone()[0]

    return {
        "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample_data": config.SAMPLE_MODE,
        "last_extracted_at": last_load,
        "rows": rows,
        "seasons": seasons,
        "dbt": _dbt_results(config.DBT_PROJECT_DIR / "target" / "run_results.json"),
    }


def publish(warehouse: str | None = None, out_dir: Path | None = None) -> dict[str, int]:
    out_dir = out_dir or output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    target_db = str(warehouse or config.WAREHOUSE_URI)
    with duckdb.connect(target_db, read_only=not target_db.startswith("md:")) as con:
        existing = {r[0] for r in con.execute(
            "select table_schema || '.' || table_name from information_schema.tables").fetchall()}
        needed = {sql.split(" from ")[1].split()[0] for sql in EXPORTS.values()}
        missing = sorted(needed - existing)
        if missing:
            raise SystemExit(
                f"Missing tables in the warehouse: {', '.join(missing)}.\n"
                "Build them first with:  python -m statcast_pipeline.transform")
        for name, sql in EXPORTS.items():
            target = (out_dir / f"{name}.parquet").as_posix()
            con.execute(f"copy ({sql}) to '{target}' (format parquet, compression zstd)")
            counts[name] = con.execute(f"select count(*) from read_parquet('{target}')").fetchone()[0]
        health = build_health(con)
    (out_dir / "health.json").write_text(json.dumps(health, indent=2, default=str))
    size_kb = sum(f.stat().st_size for f in out_dir.iterdir()) / 1024
    log.info("Published %s to %s (%.0f KB total)", counts, out_dir, size_kb)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    publish()


if __name__ == "__main__":
    main()
