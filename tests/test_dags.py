"""DAG integrity tests: the DAG files import cleanly and are wired as intended.
Skipped automatically where Airflow isn't installed (the main CI job); the
`dags` CI job installs Airflow and runs them."""

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("airflow.sdk")  # the repo's airflow/ folder alone is not Airflow

from airflow.dag_processing.dagbag import DagBag  # noqa: E402

DAGS_DIR = Path(__file__).resolve().parents[1] / "airflow" / "dags"
sys.path.insert(0, str(DAGS_DIR))


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder=str(DAGS_DIR))


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}


def test_daily_dag_shape(dagbag):
    dag = dagbag.get_dag("statcast_daily")
    assert dag.max_active_runs == 1 and not dag.catchup
    assert set(dag.get_task("resolve_dates").downstream_task_ids) == {
        "extract_pitches", "extract_games", "refresh_players"}
    assert dag.get_task("load").upstream_task_ids == {"extract_pitches", "extract_games", "refresh_players"}
    assert dag.get_task("dbt_build").upstream_task_ids == {"load"}
    assert dag.get_task("publish_dashboard_data").upstream_task_ids == {"dbt_build"}


def test_warehouse_writers_share_single_slot_pool(dagbag):
    for dag_id in ("statcast_daily", "statcast_backfill"):
        dag = dagbag.get_dag(dag_id)
        assert dag.get_task("load").pool == "duckdb_writer"
        assert dag.get_task("dbt_build").pool == "duckdb_writer"


def test_every_task_alerts_on_failure(dagbag):
    for dag in dagbag.dags.values():
        for t in dag.tasks:
            assert t.on_failure_callback, f"{dag.dag_id}.{t.task_id} has no failure alert"


def test_alert_posts_to_webhook(monkeypatch):
    import statcast_common

    sent = {}

    def fake_urlopen(req, timeout):
        sent["body"] = json.loads(req.data)

    class TI:
        dag_id, task_id, try_number = "statcast_daily", "load", 3

    class Run:
        run_id = "manual__test"

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(statcast_common.urllib.request, "urlopen", fake_urlopen)
    statcast_common.notify_failure({"task_instance": TI(), "dag_run": Run(), "exception": RuntimeError("boom")})

    assert "load" in sent["body"]["text"] and "boom" in sent["body"]["content"]
