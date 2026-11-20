-- One row per umpire assignment (game x position).
with source as (
    select * from {{ source('raw', 'game_officials') }}
)

select
    cast(game_pk as bigint)          as game_pk,
    official_type                    as umpire_position,
    cast(official_id as bigint)      as umpire_id,
    official_name                    as umpire_name,
    cast(_extracted_at as timestamp) as extracted_at
from source
qualify row_number() over (partition by game_pk, official_type order by _extracted_at desc) = 1
