"""Shared settings for the Statcast DAGs.

The pipeline runs in its own virtual environment (PIPELINE_PYTHON) rather than
Airflow's, so dbt, pandas and pybaseball can never conflict with Airflow's own
dependencies. Airflow only orchestrates: every task shells out to one of the
pipeline's CLI entry points.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import timedelta
from pathlib import Path

import pendulum

log = logging.getLogger(__name__)

TZ = pendulum.timezone("America/New_York")

# Where the repo lives and which Python runs it. Defaults suit running Airflow
# straight from a checkout; the Docker image sets both explicitly.
PIPELINE_DIR = os.environ.get("PIPELINE_DIR", str(Path(__file__).resolve().parents[2]))
PIPELINE_PYTHON = os.environ.get("PIPELINE_PYTHON", "python")

# DuckDB allows one writer at a time, so every task that writes the warehouse
# (load, dbt) runs in this single-slot pool. Created by `airflow pools set`.
WAREHOUSE_POOL = "duckdb_writer"

# Variables passed through to the pipeline's tasks.
_PASSTHROUGH = ["DATA_DIR", "WAREHOUSE_PATH", "MOTHERDUCK_TOKEN", "STATCAST_SAMPLE", "PAUSE_SECONDS"]


def pipeline_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _PASSTHROUGH if os.environ.get(k)}


def py(module: str, args: str = "") -> str:
    """Bash command that runs one pipeline module."""
    return f'"{PIPELINE_PYTHON}" -m statcast_pipeline.{module} {args}'.strip()


def notify_failure(context) -> None:
    """Post a short message to ALERT_WEBHOOK_URL (Slack or Discord incoming
    webhook) when a task fails for good. With no webhook set, it just logs."""
    ti = context["task_instance"]
    message = (
        f":rotating_light: Statcast pipeline failure\n"
        f"DAG: {ti.dag_id}  Task: {ti.task_id}  Try: {ti.try_number}\n"
        f"Run: {context['dag_run'].run_id}\n"
        f"Error: {str(context.get('exception'))[:300]}"
    )
    log.error(message)

    url = os.environ.get("ALERT_WEBHOOK_URL")
    if not url:
        return
    # "text" is what Slack reads, "content" is what Discord reads; each ignores the other.
    body = json.dumps({"text": message, "content": message}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:  # an alerting failure must never mask the real failure
        log.warning("Could not send failure alert: %s", exc)


DEFAULT_ARGS = {
    "owner": "statcast",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "on_failure_callback": notify_failure,
}
