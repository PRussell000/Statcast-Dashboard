-- Fails the build if generated sample rows are in this warehouse. Sample runs
-- (python -m statcast_pipeline.run --sample) use their own folder and pass
-- allow_sample=true, so this only fires if sample data leaks into real data.
{{ config(enabled=not var('allow_sample', false)) }}

select dt, count(*) as sample_rows
from {{ source('raw', 'pitches') }}
where _source = 'sample'
group by dt
