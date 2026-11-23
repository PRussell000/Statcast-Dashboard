"""Transform step: run dbt against the configured warehouse.

Finds the dbt executable next to the current Python interpreter first, so it
works from inside a virtual environment even when that environment's bin/
(or Scripts\\ on Windows) folder isn't on PATH - which is how Airflow calls it.

Usage:
    python -m statcast_pipeline.transform               # dbt build
    python -m statcast_pipeline.transform --full-refresh
    python -m statcast_pipeline.transform --command "source freshness"
"""

from __future__ import annotations

import argparse
import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from statcast_pipeline import config

log = logging.getLogger(__name__)


def dbt_executable() -> str:
    return shutil.which("dbt", path=str(Path(sys.executable).parent)) or shutil.which("dbt") or "dbt"


def dbt_build(full_refresh: bool = False, allow_sample: bool | None = None, command: str = "build") -> None:
    """Run a dbt command. Raises CalledProcessError if dbt fails."""
    allow_sample = config.SAMPLE_MODE if allow_sample is None else allow_sample
    env = {**os.environ, "WAREHOUSE_PATH": config.WAREHOUSE_URI}
    cmd = [dbt_executable(), *shlex.split(command),
           "--project-dir", str(config.DBT_PROJECT_DIR),
           "--profiles-dir", str(config.DBT_PROJECT_DIR)]
    if full_refresh:
        cmd.append("--full-refresh")
    if allow_sample:
        cmd += ["--vars", "{allow_sample: true}"]
    log.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, env=env, cwd=config.PROJECT_ROOT)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run dbt against the configured warehouse.")
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument("--command", default="build", help='dbt command, e.g. "build" or "source freshness"')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        dbt_build(full_refresh=args.full_refresh, command=args.command)
    except subprocess.CalledProcessError as exc:
        log.error("dbt %s failed (exit %s)", args.command, exc.returncode)
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
