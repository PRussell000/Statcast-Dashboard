-- Each pitcher's arsenal by season: usage, velocity, movement and results per
-- pitch type. Grain: pitcher x season x pitch type. Spring training and
-- exhibition games are excluded.

with pitches as (

    select f.*
    from {{ ref('fct_pitches') }} f
    where f.game_type not in ('S', 'E', 'A')
      and f.pitch_type is not null

),

by_pitch as (

    select
        pitcher_id,
        season,
        pitch_type,
        max(pitch_name)                                         as pitch_name,
        count(*)                                                as pitches,
        avg(release_speed_mph)                                  as avg_velocity_mph,
        max(release_speed_mph)                                  as max_velocity_mph,
        avg(spin_rate_rpm)                                      as avg_spin_rpm,
        avg(horizontal_break_in)                                as avg_horizontal_break_in,
        avg(induced_vertical_break_in)                          as avg_induced_vertical_break_in,
        count(*) filter (where is_swing)                        as swings,
        count(*) filter (where is_whiff)                        as whiffs,
        count(*) filter (where is_whiff or is_called_strike)    as called_plus_swinging_strikes,
        count(*) filter (where is_in_zone)                      as in_zone_pitches,
        avg(xwoba) filter (where is_in_play)                    as xwoba_on_contact,
        -sum(batter_run_value)                                  as pitcher_run_value
    from pitches
    group by pitcher_id, season, pitch_type

)

select
    b.pitcher_id || '-' || b.season || '-' || b.pitch_type     as arsenal_key,
    b.pitcher_id,
    p.full_name                                                 as pitcher_name,
    b.season,
    b.pitch_type,
    b.pitch_name,
    b.pitches,
    b.pitches / sum(b.pitches) over (partition by b.pitcher_id, b.season)  as usage_rate,
    round(b.avg_velocity_mph, 1)                                as avg_velocity_mph,
    round(b.max_velocity_mph, 1)                                as max_velocity_mph,
    round(b.avg_spin_rpm, 0)                                    as avg_spin_rpm,
    round(b.avg_horizontal_break_in, 1)                         as avg_horizontal_break_in,
    round(b.avg_induced_vertical_break_in, 1)                   as avg_induced_vertical_break_in,
    b.in_zone_pitches / b.pitches                               as zone_rate,
    case when b.swings > 0 then b.whiffs / b.swings end         as whiff_rate,
    b.called_plus_swinging_strikes / b.pitches                  as csw_rate,
    round(b.xwoba_on_contact, 3)                                as xwoba_on_contact,
    round(100.0 * b.pitcher_run_value / b.pitches, 2)           as run_value_per_100
from by_pitch b
left join {{ ref('dim_players') }} p on p.player_id = b.pitcher_id
