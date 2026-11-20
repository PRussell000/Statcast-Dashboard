{{
  config(
    materialized = 'incremental',
    unique_key = 'pitch_id',
    incremental_strategy = 'delete+insert',
    on_schema_change = 'append_new_columns'
  )
}}

-- The central fact table. Grain: one row per pitch.
--
-- Incremental logic: on each run, process only rows that were extracted after
-- the newest row already in this table (this catches new days AND backfilled
-- older seasons), plus a short lookback window of recent game dates to pick up
-- late corrections. delete+insert on pitch_id makes re-processing safe.

with pitches as (

    select * from {{ ref('stg_pitches') }}

    {% if is_incremental() %}
    where extracted_at > (select max(extracted_at) from {{ this }})
       or game_date >= (select max(game_date) from {{ this }}) - {{ var('incremental_lookback_days') }}
    {% endif %}

)

select
    -- keys
    pitch_id,
    game_pk,
    at_bat_number,
    pitch_number,
    pitcher_id,
    batter_id,
    catcher_id,

    -- context
    game_date,
    game_year                                   as season,
    game_type,
    inning,
    inning_half,
    outs,
    balls,
    strikes,
    pitcher_hand,
    batter_side,

    -- pitch
    pitch_type,
    pitch_name,
    release_speed_mph,
    spin_rate_rpm,
    release_extension_ft,
    horizontal_break_ft * 12                    as horizontal_break_in,
    induced_vertical_break_ft * 12              as induced_vertical_break_in,
    plate_x_ft,
    plate_z_ft,
    strike_zone_top_ft,
    strike_zone_bottom_ft,
    {{ in_rulebook_zone('plate_x_ft', 'plate_z_ft', 'strike_zone_top_ft', 'strike_zone_bottom_ft') }}
                                                as is_in_zone,

    -- result flags
    pitch_result,
    pitch_result in ('swinging_strike', 'swinging_strike_blocked', 'foul', 'foul_tip',
                     'foul_bunt', 'missed_bunt', 'bunt_foul_tip', 'hit_into_play')
                                                as is_swing,
    pitch_result in ('swinging_strike', 'swinging_strike_blocked', 'missed_bunt')
                                                as is_whiff,
    pitch_result = 'called_strike'              as is_called_strike,
    pitch_result_code = 'X'                     as is_in_play,
    plate_appearance_event,
    batted_ball_type,
    exit_velocity_mph,
    launch_angle_deg,
    xwoba,
    run_value                                   as batter_run_value,

    extracted_at
from pitches
