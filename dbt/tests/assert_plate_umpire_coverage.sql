-- Warn if more than 5% of regular-season games with tracked pitches have no
-- home-plate umpire: that points to a gap in the umpire extract.
{{ config(severity='warn') }}

select
    count(*)                                                     as games,
    count(*) filter (where home_plate_umpire_id is null)         as games_without_umpire
from {{ ref('dim_games') }}
where game_type = 'R'
having count(*) filter (where home_plate_umpire_id is null) > 0.05 * count(*)
