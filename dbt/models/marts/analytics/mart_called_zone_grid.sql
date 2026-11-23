-- Called pitches binned on a grid around the strike zone, for heatmaps.
-- Horizontal: 2-inch bins of plate_x (catcher's view, 0 = middle of the plate).
-- Vertical: position normalized to each batter's own zone (0 = bottom, 1 = top),
-- in 0.1 bins, so tall and short batters line up on one picture.
--
-- Three slices share the grain (season x scope x umpire x count x bin):
--   scope = 'league', count_state = 'all'   league-wide, all counts
--   scope = 'league', count_state = '0-2'…  league-wide, one count
--   scope = 'umpire', count_state = 'all'   one umpire, all counts
-- Regular season only.

with binned as (

    select
        game_year                                                       as season,
        umpire_id,
        umpire_name,
        count_state,
        floor(plate_x_ft * 12 / 2) * 2 + 1                              as x_in,
        floor((plate_z_ft - strike_zone_bottom_ft)
              / nullif(strike_zone_top_ft - strike_zone_bottom_ft, 0) * 10) / 10 + 0.05
                                                                        as z_norm,
        is_called_strike,
        is_in_zone,
        is_correct_call
    from {{ ref('int_called_pitches') }}
    where game_type = 'R'
      and abs(plate_x_ft * 12) < 20

),

in_frame as (

    select * from binned where z_norm between -0.5 and 1.5

),

sliced as (

    select season, 'league' as scope, null::bigint as umpire_id, null as umpire_name, 'all' as count_state,
           x_in, z_norm, is_called_strike, is_in_zone, is_correct_call
    from in_frame

    union all

    select season, 'league', null, null, count_state,
           x_in, z_norm, is_called_strike, is_in_zone, is_correct_call
    from in_frame

    union all

    select season, 'umpire', umpire_id, umpire_name, 'all',
           x_in, z_norm, is_called_strike, is_in_zone, is_correct_call
    from in_frame
    where umpire_id is not null

)

select
    season || '-' || scope || '-' || coalesce(umpire_id::varchar, 'all') || '-' || count_state
        || '-' || x_in || '-' || round(z_norm, 2)                        as grid_key,
    season,
    scope,
    umpire_id,
    max(umpire_name)                                                    as umpire_name,
    count_state,
    x_in,
    round(z_norm, 2)                                                    as z_norm,
    count(*)                                                            as takes,
    count(*) filter (where is_called_strike)                            as called_strikes,
    count(*) filter (where not is_correct_call)                         as missed_calls,
    avg(is_called_strike::int)                                          as called_strike_rate,
    avg(is_in_zone::int)                                                as in_zone_share
from sliced
group by season, scope, umpire_id, count_state, x_in, round(z_norm, 2)
