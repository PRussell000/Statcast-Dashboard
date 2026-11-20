FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so code changes don't bust the pip cache layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DATA_DIR=/app/data \
    WAREHOUSE_PATH=/app/warehouse/statcast.duckdb \
    PYTHONUNBUFFERED=1

# Default: process yesterday. Override with e.g.
#   docker compose run --rm pipeline --start 2024-06-01 --end 2024-06-07
ENTRYPOINT ["python", "-m", "statcast_pipeline.run"]
