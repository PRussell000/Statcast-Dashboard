-- Singular test: returns rows that FAIL. Real MLB pitches fall roughly between
-- 35 mph (eephus / position-player pitching) and 106 mph.
select pitch_id, release_speed_mph
from {{ ref('stg_pitches') }}
where release_speed_mph is not null
  and (release_speed_mph < 30 or release_speed_mph > 110)
