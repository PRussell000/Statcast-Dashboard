-- Singular test: a loaded game day with very few pitches usually means a
-- truncated or failed download, not a real light day.
{{ config(severity='warn') }}

select game_date, count(*) as pitches
from {{ ref('stg_pitches') }}
group by game_date
having count(*) < 100
