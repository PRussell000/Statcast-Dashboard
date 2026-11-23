-- Fails if more than 0.01% of pitches have an implausible speed. A handful is
-- normal; a large share means a broken download or a unit change upstream.
-- Scales with the data: 0.01% of 2.3M pitches = 230.
with stats as (
    select
        count(*)                                                        as pitches,
        count(*) filter (where release_speed_mph < 30 or release_speed_mph > 110) as outliers
    from {{ ref('stg_pitches') }}
    where release_speed_mph is not null
)
select *, outliers / pitches as outlier_share
from stats
where pitches > 0 and outliers / pitches > 0.0001
