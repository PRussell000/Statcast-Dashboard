"""Backfill whole Statcast seasons on demand.

Trigger with config, e.g. {"seasons": [2023, 2024, 2025]}:

    plan_seasons ── extract_season[2023] ┐
                    extract_season[2024] ├── refresh_players ── load ── dbt_build ── publish
                    extract_season[2025] ┘

extract_season is dynamically mapped: one task instance per season, run one at
a time so the sources aren't hammered. Each is resumable (days already on disk
are skipped), so clearing a failed season simply continues where it stopped.
"""

from __future__ import annotations

from datetime import date, timedelta

import pendulum
from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import Param, dag, get_current_context, task
from statcast_common import DEFAULT_ARGS, PIPELINE_DIR, TZ, WAREHOUSE_POOL, pipeline_env, py

FIRST_STATCAST_SEASON = 2015


@dag(
    dag_id="statcast_backfill",
    description="Backfill one or more Statcast seasons, then load and dbt build once",
    schedule=None,                    # manual only
    start_date=pendulum.datetime(2026, 1, 1, tz=TZ),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["statcast", "backfill"],
    doc_md=__doc__,
    params={
        "seasons": Param([date.today().year - 1], type="array", items={"type": "integer"},
                         title="Seasons", description=f"Statcast starts in {FIRST_STATCAST_SEASON}."),
        "force": Param(False, type="boolean", title="Re-pull days already on disk"),
    },
)
def statcast_backfill():
    common = {"cwd": PIPELINE_DIR, "env": pipeline_env(), "append_env": True}

    @task(retries=0)
    def plan_seasons() -> list[str]:
        """Validate the requested seasons and build one extract command per season."""
        params = get_current_context()["params"]
        seasons = sorted({int(s) for s in params["seasons"]})
        bad = [s for s in seasons if s < FIRST_STATCAST_SEASON or s > date.today().year]
        if bad:
            raise ValueError(f"Seasons outside {FIRST_STATCAST_SEASON}-{date.today().year}: {bad}")
        force = "--force" if params["force"] else ""
        return [py("backfill", f"--seasons {s} --extract-only {force}") for s in seasons]

    extract_season = BashOperator.partial(
        task_id="extract_season",
        max_active_tis_per_dag=1,                 # one season at a time
        execution_timeout=timedelta(hours=4),
        map_index_template="{{ task.bash_command.split('--seasons ')[1].split()[0] }}",
        **common,
    ).expand(bash_command=plan_seasons())

    refresh_players = BashOperator(task_id="refresh_players", bash_command=py("extract_players"),
                                   retries=0, **common)
    load = BashOperator(task_id="load", bash_command=py("load"), pool=WAREHOUSE_POOL, **common)
    dbt_build = BashOperator(task_id="dbt_build", bash_command=py("transform"), pool=WAREHOUSE_POOL,
                             retries=0, execution_timeout=timedelta(hours=1), **common)

    publish_dashboard_data = BashOperator(task_id="publish_dashboard_data", bash_command=py("publish"),
                                          pool=WAREHOUSE_POOL, **common)

    extract_season >> refresh_players >> load >> dbt_build >> publish_dashboard_data


statcast_backfill()
