# Airflow image with the Statcast pipeline installed in its OWN virtual
# environment (/opt/pipeline-venv). Airflow orchestrates; the pipeline's
# dependencies (dbt, pandas<3, pybaseball) never touch Airflow's.
ARG AIRFLOW_VERSION=3.4.0
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12

USER root
RUN python -m venv /opt/pipeline-venv && chown -R airflow:0 /opt/pipeline-venv
USER airflow

COPY --chown=airflow:0 requirements.txt /tmp/pipeline-requirements.txt
RUN /opt/pipeline-venv/bin/pip install --no-cache-dir -r /tmp/pipeline-requirements.txt
