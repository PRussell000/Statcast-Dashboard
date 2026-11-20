-- One clean row per pitch: explicit types, clear names, duplicates removed.
-- Explicit casts make the model robust to Savant schema drift across seasons
-- (columns added, or a column that is entirely null on a given day).

with source as (

    select * from {{ source('raw', 'pitches') }}

),

typed as (

    select
        -- keys
        cast(game_pk as bigint)                         as game_pk,
        cast(at_bat_number as integer)                  as at_bat_number,
        cast(pitch_number as integer)                   as pitch_number,
        cast(game_pk as varchar) || '-'
            || cast(cast(at_bat_number as integer) as varchar) || '-'
            || cast(cast(pitch_number as integer) as varchar)
                                                        as pitch_id,

        -- game context
        cast(game_date as date)                         as game_date,
        cast(game_year as integer)                      as game_year,
        game_type,
        home_team,
        away_team,
        cast(inning as integer)                         as inning,
        inning_topbot                                   as inning_half,
        cast(outs_when_up as integer)                   as outs,
        cast(balls as integer)                          as balls,
        cast(strikes as integer)                        as strikes,

        -- players
        cast(pitcher as bigint)                         as pitcher_id,
        player_name                                     as pitcher_name,
        cast(batter as bigint)                          as batter_id,
        cast(fielder_2 as bigint)                       as catcher_id,
        p_throws                                        as pitcher_hand,
        stand                                           as batter_side,

        -- pitch characteristics
        pitch_type,
        pitch_name,
        cast(release_speed as double)                   as release_speed_mph,
        cast(effective_speed as double)                 as effective_speed_mph,
        cast(release_spin_rate as double)               as spin_rate_rpm,
        cast(spin_axis as double)                       as spin_axis_deg,
        cast(release_extension as double)               as release_extension_ft,
        cast(release_pos_x as double)                   as release_pos_x_ft,
        cast(release_pos_z as double)                   as release_pos_z_ft,
        cast(pfx_x as double)                           as horizontal_break_ft,
        cast(pfx_z as double)                           as induced_vertical_break_ft,

        -- location (catcher's view, feet; 0 = middle of the plate)
        cast(plate_x as double)                         as plate_x_ft,
        cast(plate_z as double)                         as plate_z_ft,
        cast(sz_top as double)                          as strike_zone_top_ft,
        cast(sz_bot as double)                          as strike_zone_bottom_ft,
        cast(zone as integer)                           as gameday_zone,

        -- outcome
        description                                     as pitch_result,
        type                                            as pitch_result_code,   -- B / S / X
        events                                          as plate_appearance_event,
        bb_type                                         as batted_ball_type,
        cast(launch_speed as double)                    as exit_velocity_mph,
        cast(launch_angle as double)                    as launch_angle_deg,
        cast(hit_distance_sc as double)                 as hit_distance_ft,
        cast(estimated_woba_using_speedangle as double) as xwoba,
        cast(delta_run_exp as double)                   as run_value,

        -- load metadata
        cast(_extracted_at as timestamp)                as extracted_at

    from source

),

deduplicated as (

    -- If a day was re-extracted and somehow loaded twice, keep the newest copy.
    select *
    from typed
    qualify row_number() over (
        partition by game_pk, at_bat_number, pitch_number
        order by extracted_at desc
    ) = 1

)

select * from deduplicated
