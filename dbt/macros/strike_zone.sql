{#
  Strike-zone helpers, defined once so every model uses the same geometry.
  Coordinates are Statcast's: feet, catcher's view, plate_x = 0 at the middle
  of the plate; sz_top / sz_bot are set per batter.
#}

{% macro zone_pad_ft() -%}
    ({{ var('ball_radius_in') }} / 12.0)
{%- endmacro %}

{% macro in_rulebook_zone(plate_x, plate_z, sz_top, sz_bot) -%}
    (
        abs({{ plate_x }}) <= ({{ var('plate_half_width_in') }} + {{ var('ball_radius_in') }}) / 12.0
        and {{ plate_z }} between {{ sz_bot }} - {{ zone_pad_ft() }} and {{ sz_top }} + {{ zone_pad_ft() }}
    )
{%- endmacro %}

{#
  Signed distance to the (padded) zone edge, in inches: positive = inside,
  negative = outside. Uses the tighter of the horizontal and vertical margins,
  which is exact for pitches beside or above/below the zone and a slight
  underestimate of distance off the corners.
#}
{% macro zone_edge_distance_in(plate_x, plate_z, sz_top, sz_bot) -%}
    12.0 * least(
        ({{ var('plate_half_width_in') }} + {{ var('ball_radius_in') }}) / 12.0 - abs({{ plate_x }}),
        {{ plate_z }} - ({{ sz_bot }} - {{ zone_pad_ft() }}),
        ({{ sz_top }} + {{ zone_pad_ft() }}) - {{ plate_z }}
    )
{%- endmacro %}
