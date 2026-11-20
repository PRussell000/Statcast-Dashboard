-- How consistent is each pitch type's movement for the pitchers who throw it?
-- For every pitcher-season-pitch type with at least 50 pitches, take the
-- standard deviation of horizontal and vertical break, then average across
-- pitchers. Knuckleballs should stand out as far less predictable.
-- Grain: season x pitch type.

with per_pitcher as (

    select
        season,
        pitch_type,
        pitcher_id,
        max(pitch_name)                          as pitch_name,
        count(*)                                 as pitches,
        avg(release_speed_mph)                   as avg_velocity_mph,
        stddev_samp(horizontal_break_in)         as sd_horizontal_break_in,
        stddev_samp(induced_vertical_break_in)   as sd_induced_vertical_break_in
    from {{ ref('fct_pitches') }}
    where game_type not in ('S', 'E', 'A')
      and pitch_type is not null
      and horizontal_break_in is not null
    group by season, pitch_type, pitcher_id
    having count(*) >= 50

)

select
    season || '-' || pitch_type                         as season_pitch_key,
    season,
    pitch_type,
    max(pitch_name)                                     as pitch_name,
    count(*)                                            as pitchers,
    sum(pitches)                                        as pitches,
    round(avg(avg_velocity_mph), 1)                     as avg_velocity_mph,
    round(avg(sd_horizontal_break_in), 2)               as avg_sd_horizontal_break_in,
    round(avg(sd_induced_vertical_break_in), 2)         as avg_sd_induced_vertical_break_in,
    round(sqrt(avg(sd_horizontal_break_in ^ 2 + sd_induced_vertical_break_in ^ 2)), 2)
                                                        as movement_spread_in
from per_pitcher
group by season, pitch_type
