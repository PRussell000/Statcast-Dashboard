-- Warn if more than 2% of regular-season games with tracked pitches have no
-- home-plate umpire (a gap in the umpire extract); fail above 10%.
-- Percentages, not row counts, so the check behaves the same for one week or ten seasons.
{{ config(severity='error', warn_if='>0', error_if='>1') }}

with coverage as (
    select
        count(*)                                                 as games,
        count(*) filter (where home_plate_umpire_id is null)     as games_without_umpire
    from {{ ref('dim_games') }}
    where game_type = 'R'
)
select 'warn' as level, games, games_without_umpire
from coverage
where games_without_umpire > 0.02 * games
union all
select 'error', games, games_without_umpire
from coverage
where games_without_umpire > 0.10 * games
