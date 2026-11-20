-- One row per scheduled game from the MLB Stats API.
with source as (
    select * from {{ source('raw', 'games') }}
)

select
    cast(game_pk as bigint)             as game_pk,
    cast(official_date as date)         as game_date,
    cast(game_datetime_utc as timestamp) as game_start_utc,
    game_type,
    status                              as game_status,
    cast(home_team_id as bigint)        as home_team_id,
    home_team_name,
    cast(away_team_id as bigint)        as away_team_id,
    away_team_name,
    venue_name,
    double_header,
    cast(game_number as integer)        as game_number,
    cast(_extracted_at as timestamp)    as extracted_at
from source
qualify row_number() over (partition by game_pk order by _extracted_at desc) = 1
