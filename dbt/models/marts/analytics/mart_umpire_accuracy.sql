-- Home-plate umpire accuracy by season, versus the rulebook zone.
-- Grain: umpire x season. Filter on called_pitches in the dashboard (e.g. >= 1,000)
-- before ranking, so small samples don't top the leaderboard.

with calls as (

    select *
    from {{ ref('int_called_pitches') }}
    where umpire_id is not null
      and game_type not in ('S', 'E', 'A')

),

by_umpire as (

    select
        umpire_id,
        max(umpire_name)                                                    as umpire_name,
        game_year                                                           as season,
        count(distinct game_pk)                                             as games,
        count(*)                                                            as called_pitches,
        count(*) filter (where is_correct_call)                             as correct_calls,
        count(*) filter (where miss_type = 'missed_strike')                 as missed_strikes,
        count(*) filter (where miss_type = 'missed_ball')                   as missed_balls,
        count(*) filter (where is_edge_pitch)                               as edge_pitches,
        count(*) filter (where is_edge_pitch and is_correct_call)           as edge_correct,
        count(*) filter (where strikes = 2)                                 as two_strike_calls,
        count(*) filter (where strikes = 2 and is_correct_call)             as two_strike_correct,
        count(*) filter (where balls = 3)                                   as three_ball_calls,
        count(*) filter (where balls = 3 and is_correct_call)               as three_ball_correct
    from calls
    group by umpire_id, game_year

)

select
    umpire_id || '-' || season                                              as umpire_season_key,
    umpire_id,
    umpire_name,
    season,
    games,
    called_pitches,
    correct_calls / called_pitches                                          as accuracy,
    correct_calls / called_pitches
        - sum(correct_calls) over (partition by season)
          / sum(called_pitches) over (partition by season)                  as accuracy_vs_league,
    missed_strikes,
    missed_balls,
    round(called_pitches / games, 1)                                        as called_pitches_per_game,
    round((missed_strikes + missed_balls) / games, 2)                       as missed_calls_per_game,
    edge_pitches,
    case when edge_pitches > 0 then edge_correct / edge_pitches end         as edge_accuracy,
    case when two_strike_calls > 0 then two_strike_correct / two_strike_calls end   as two_strike_accuracy,
    case when three_ball_calls > 0 then three_ball_correct / three_ball_calls end   as three_ball_accuracy
from by_umpire
