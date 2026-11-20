-- Player names and cross-site IDs from the Chadwick Bureau register.
with source as (
    select * from {{ source('raw', 'players') }}
)

select
    cast(key_mlbam as bigint)                          as player_id,
    name_first                                         as first_name,
    name_last                                          as last_name,
    trim(coalesce(name_first, '') || ' ' || coalesce(name_last, '')) as full_name,
    nullif(cast(key_fangraphs as bigint), -1)          as fangraphs_id,
    key_bbref                                          as bbref_id,
    cast(mlb_played_first as integer)                  as mlb_first_season,
    cast(mlb_played_last as integer)                   as mlb_last_season
from source
where cast(key_mlbam as bigint) > 0
qualify row_number() over (partition by key_mlbam order by mlb_played_last desc nulls last) = 1
