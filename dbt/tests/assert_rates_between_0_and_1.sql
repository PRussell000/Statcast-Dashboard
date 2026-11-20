-- Every rate in the analytics marts must be a proportion. Returns failing rows.
select 'mart_pitcher_arsenal' as model, arsenal_key as row_key
from {{ ref('mart_pitcher_arsenal') }}
where usage_rate not between 0 and 1
   or zone_rate not between 0 and 1
   or whiff_rate not between 0 and 1
   or csw_rate not between 0 and 1

union all

select 'mart_umpire_accuracy', umpire_season_key
from {{ ref('mart_umpire_accuracy') }}
where accuracy not between 0 and 1
   or edge_accuracy not between 0 and 1
   or two_strike_accuracy not between 0 and 1
   or three_ball_accuracy not between 0 and 1

union all

select 'mart_called_accuracy_by_count', season_count_key
from {{ ref('mart_called_accuracy_by_count') }}
where accuracy not between 0 and 1
