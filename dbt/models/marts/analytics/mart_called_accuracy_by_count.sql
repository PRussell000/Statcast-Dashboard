-- League-wide call accuracy by ball-strike count. Answers "where do umpires
-- miss?" (e.g., do they shrink the zone with two strikes?). Grain: season x count.

with calls as (

    select *
    from {{ ref('int_called_pitches') }}
    where game_type not in ('S', 'E', 'A')

)

select
    game_year || '-' || count_state                                         as season_count_key,
    game_year                                                               as season,
    count_state,
    balls,
    strikes,
    count(*)                                                                as called_pitches,
    avg(is_correct_call::int)                                               as accuracy,
    -- miss_type is null for correct calls, so coalesce before averaging.
    -- Of takes inside the zone, how often was it called a ball?
    avg(coalesce(miss_type = 'missed_strike', false)::int) filter (where is_in_zone)
                                                                            as in_zone_called_ball_rate,
    -- Of takes outside the zone, how often was it called a strike?
    avg(coalesce(miss_type = 'missed_ball', false)::int) filter (where not is_in_zone)
                                                                            as out_of_zone_called_strike_rate,
    avg(is_correct_call::int) filter (where is_edge_pitch)                  as edge_accuracy
from calls
group by game_year, count_state, balls, strikes
