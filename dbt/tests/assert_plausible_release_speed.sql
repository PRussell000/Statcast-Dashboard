-- Lists pitches outside 30-110 mph. Real data has a few (position players
-- lobbing in blowouts, eephus pitches, tracking glitches), so this only WARNS.
-- assert_release_speed_outlier_share fails the build if they become common.
{{ config(severity='warn') }}

select pitch_id, game_date, pitcher_name, pitch_name, release_speed_mph
from {{ ref('stg_pitches') }}
where release_speed_mph is not null
  and (release_speed_mph < 30 or release_speed_mph > 110)
