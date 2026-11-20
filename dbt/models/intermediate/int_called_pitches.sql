-- Every pitch the home-plate umpire had to call (no swing), with the rulebook
-- zone verdict and whether the umpire got it right. Grain: pitch.
--
-- Excludes automatic balls/strikes (pitch-clock violations) and pitches
-- missing location or zone data.

with called as (

    select *
    from {{ ref('stg_pitches') }}
    where pitch_result in ('called_strike', 'ball', 'blocked_ball')
      and plate_x_ft is not null
      and plate_z_ft is not null
      and strike_zone_top_ft is not null
      and strike_zone_bottom_ft is not null

),

plate_umpires as (

    select game_pk, umpire_id, umpire_name
    from {{ ref('stg_game_officials') }}
    where umpire_position = 'Home Plate'

),

scored as (

    select
        c.pitch_id,
        c.game_pk,
        c.game_date,
        c.game_year,
        c.game_type,
        c.pitcher_id,
        c.batter_id,
        c.catcher_id,
        c.batter_side,
        c.pitch_type,
        c.balls,
        c.strikes,
        c.balls || '-' || c.strikes                               as count_state,
        c.plate_x_ft,
        c.plate_z_ft,
        c.strike_zone_top_ft,
        c.strike_zone_bottom_ft,
        u.umpire_id,
        u.umpire_name,

        c.pitch_result = 'called_strike'                          as is_called_strike,
        {{ in_rulebook_zone('c.plate_x_ft', 'c.plate_z_ft',
                            'c.strike_zone_top_ft', 'c.strike_zone_bottom_ft') }}
                                                                  as is_in_zone,
        {{ zone_edge_distance_in('c.plate_x_ft', 'c.plate_z_ft',
                                 'c.strike_zone_top_ft', 'c.strike_zone_bottom_ft') }}
                                                                  as zone_edge_distance_in
    from called c
    left join plate_umpires u using (game_pk)

)

select
    *,
    is_called_strike = is_in_zone                                 as is_correct_call,
    case
        when is_in_zone and not is_called_strike then 'missed_strike'   -- strike called a ball
        when not is_in_zone and is_called_strike then 'missed_ball'     -- ball called a strike
    end                                                           as miss_type,
    abs(zone_edge_distance_in) <= {{ var('edge_band_in') }}       as is_edge_pitch
from scored
