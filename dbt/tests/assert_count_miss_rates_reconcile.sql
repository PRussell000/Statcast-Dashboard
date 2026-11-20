-- The two miss rates must reconcile with overall accuracy: misses inside the
-- zone plus misses outside it equal all misses. Catches null-handling bugs
-- (e.g. averaging a flag that is null for correct calls).
with c as (
    select
        season_count_key,
        called_pitches,
        accuracy,
        in_zone_called_ball_rate,
        out_of_zone_called_strike_rate
    from {{ ref('mart_called_accuracy_by_count') }}
),
truth as (
    select
        game_year || '-' || count_state                         as season_count_key,
        count(*) filter (where is_in_zone)                      as in_zone,
        count(*) filter (where not is_in_zone)                  as out_zone
    from {{ ref('int_called_pitches') }}
    where game_type not in ('S', 'E', 'A')
    group by 1
)
select c.*
from c join truth t using (season_count_key)
where abs(
    (1 - c.accuracy) * c.called_pitches
    - (coalesce(c.in_zone_called_ball_rate, 0) * t.in_zone
       + coalesce(c.out_of_zone_called_strike_rate, 0) * t.out_zone)
) > 0.5
