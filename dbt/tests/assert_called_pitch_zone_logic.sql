-- Sanity check on the zone math: a pitch over the middle of the plate at
-- mid-zone height must be in the zone, and one 2 feet outside must not be.
-- Returns rows only if the macro is broken.
with probes as (
    select 0.0 as plate_x, 2.5 as plate_z, 3.5 as sz_top, 1.5 as sz_bot, true as expected
    union all select 2.0, 2.5, 3.5, 1.5, false
    union all select 0.0, 4.0, 3.5, 1.5, false
    union all select 0.82, 2.5, 3.5, 1.5, true    -- just inside: ball clips the edge
)
select *
from probes
where {{ in_rulebook_zone('plate_x', 'plate_z', 'sz_top', 'sz_bot') }} != expected
