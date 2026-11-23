"""Daily Statcast pipeline.

Every morning from March through November, load yesterday's games:

    resolve_dates ─┬─ extract_pitches ──┐
                   ├─ extract_games ────┼── load ── dbt_build
                   └─ refresh_players ──┘          └─ publish_dashboard_data

* The three extracts hit different sources, so they run in parallel.
* load and dbt_build share a one-slot pool because DuckDB allows one writer.
* Re-running any date is safe: extracts overwrite only that day's partition,
  and the dbt fact model replaces rows by pitch_id.

Manual runs ("Trigger DAG w/ config") can set start/end to replay a date range,
which is how the pipeline is demoed in the off-season.
"""

from __future__ import annotations

from datetime import date, timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag, get_current_context, task
from statcast_common import DEFAULT_ARGS, PIPELINE_DIR, TZ, WAREHOUSE_POOL, pipeline_env, py

DATES = "--start {{ ti.xcom_pull(task_ids='resolve_dates')['start'] }} " \
        "--end {{ ti.xcom_pull(task_ids='resolve_dates')['end'] }}"
FORCE = "{{ '--force' if params.force else '' }}"


@dag(
    dag_id="statcast_daily",
    description="Extract yesterday's Statcast pitches, games and umpires; load to DuckDB; dbt build",
    schedule="0 10 * 3-11 *",          # 10:00 ET daily, March-November
    start_date=pendulum.datetime(2026, 3, 1, tz=TZ),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    dagrun_timeout=timedelta(hours=2),
    tags=["statcast", "daily"],
    doc_md=__doc__,
    params={
        "start": Param("", type="string", title="Start date (YYYY-MM-DD)",
                       description="Leave blank for yesterday. Set to replay a date range."),
        "end": Param("", type="string", title="End date (YYYY-MM-DD)", description="Defaults to start."),
        "force": Param(False, type="boolean", title="Re-pull days already on disk"),
        "full_refresh": Param(False, type="boolean", title="Rebuild incremental dbt models from scratch"),
    },
)
def statcast_daily():

    @task(retries=0)   # bad dates won't fix themselves on retry
    def resolve_dates() -> dict[str, str]:
        """Yesterday in Eastern time, unless start/end were given."""
        ctx = get_current_context()
        params = ctx["params"]
        if params.get("start"):
            start = date.fromisoformat(params["start"])
            end = date.fromisoformat(params["end"]) if params.get("end") else start
        else:
            # Manual runs in Airflow 3 can have no logical date; fall back to run_after.
            ref = ctx.get("logical_date") or ctx["dag_run"].run_after
            start = end = (pendulum.instance(ref).in_timezone(TZ) - timedelta(days=1)).date()
        if end < start:
            raise ValueError(f"end {end} is before start {start}")
        return {"start": start.isoformat(), "end": end.isoformat()}

    common = {"cwd": PIPELINE_DIR, "env": pipeline_env(), "append_env": True}

    extract_pitches = BashOperator(
        task_id="extract_pitches",
        bash_command=py("extract", f"{DATES} {FORCE}"),
        execution_timeout=timedelta(minutes=45),
        **common,
    )
    extract_games = BashOperator(
        task_id="extract_games",
        bash_command=py("extract_games", f"{DATES} {FORCE}"),
        execution_timeout=timedelta(minutes=20),
        **common,
    )
    refresh_players = BashOperator(
        task_id="refresh_players",
        bash_command=py("extract_players"),   # skips if under 7 days old; never fails the run
        execution_timeout=timedelta(minutes=10),
        retries=0,
        **common,
    )
    load = BashOperator(
        task_id="load",
        bash_command=py("load"),
        pool=WAREHOUSE_POOL,
        execution_timeout=timedelta(minutes=20),
        **common,
    )
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=py("transform", "{{ '--full-refresh' if params.full_refresh else '' }}"),
        pool=WAREHOUSE_POOL,
        execution_timeout=timedelta(minutes=45),
        retries=0,   # a failed data test won't fix itself; alert immediately
        **common,
    )

    publish_dashboard_data = BashOperator(
        task_id="publish_dashboard_data",
        bash_command=py("publish"),
        pool=WAREHOUSE_POOL,
        execution_timeout=timedelta(minutes=10),
        **common,
    )

    (resolve_dates() >> [extract_pitches, extract_games, refresh_players] >> load >> dbt_build
     >> publish_dashboard_data)


statcast_daily()
