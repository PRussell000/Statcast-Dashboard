-- One row per game that has tracked pitches, enriched with schedule details
-- and the home-plate umpire. Grain: game.

with from_pitches as (

    select
        game_pk,
        min(game_date)          as game_date,
        min(game_year)          as season,
        min(game_type)          as game_type,
        min(home_team)          as home_team,
        min(away_team)          as away_team,
        count(*)                as pitches_tracked
    from {{ ref('stg_pitches') }}
    group by game_pk

),

plate_umpires as (

    select game_pk, umpire_id, umpire_name
    from {{ ref('stg_game_officials') }}
    where umpire_position = 'Home Plate'

)

select
    p.game_pk,
    p.game_date,
    p.season,
    p.game_type,
    p.home_team,
    p.away_team,
    g.home_team_name,
    g.away_team_name,
    g.venue_name,
    g.game_status,
    g.game_start_utc,
    g.double_header,
    g.game_number,
    u.umpire_id                     as home_plate_umpire_id,
    u.umpire_name                   as home_plate_umpire_name,
    p.pitches_tracked,
    g.game_pk is not null           as has_schedule_data
from from_pitches p
left join {{ ref('stg_games') }} g using (game_pk)
left join plate_umpires u using (game_pk)
