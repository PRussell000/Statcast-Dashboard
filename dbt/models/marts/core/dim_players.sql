-- One row per player who appears in the pitch data as a pitcher or batter.
-- Names come from the Chadwick register; if a player is missing there, pitchers
-- fall back to Statcast's "Last, First" name. Grain: player.

with appearances as (

    select pitcher_id as player_id, game_date, 'pitcher' as role, pitcher_name as statcast_name
    from {{ ref('stg_pitches') }}
    union all
    select batter_id, game_date, 'batter', null
    from {{ ref('stg_pitches') }}

),

rolled_up as (

    select
        player_id,
        min(game_date)                                  as first_tracked_date,
        max(game_date)                                  as last_tracked_date,
        count(*) filter (where role = 'pitcher')        as pitches_thrown,
        count(*) filter (where role = 'batter')         as pitches_seen,
        max(statcast_name)                              as statcast_name
    from appearances
    where player_id is not null
    group by player_id

)

select
    r.player_id,
    coalesce(
        p.full_name,
        -- "Wheeler, Zack" -> "Zack Wheeler"
        trim(split_part(r.statcast_name, ',', 2)) || ' ' || trim(split_part(r.statcast_name, ',', 1))
    )                                                   as full_name,
    p.first_name,
    p.last_name,
    case
        when p.player_id is not null then 'chadwick_register'
        when r.statcast_name is not null then 'statcast'
        else 'unknown'
    end                                                 as name_source,
    r.pitches_thrown > 0                                as is_pitcher,
    r.pitches_seen > 0                                  as is_batter,
    r.pitches_thrown,
    r.pitches_seen,
    r.first_tracked_date,
    r.last_tracked_date,
    p.fangraphs_id,
    p.bbref_id,
    p.mlb_first_season,
    p.mlb_last_season
from rolled_up r
left join {{ ref('stg_players') }} p using (player_id)
