"""Dashboard pages and data loading. app.py wires these into navigation;
tests call each page function directly."""

from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from charts import called_strike_heatmap, count_bars, difference_heatmap, movement_plot, spread_bars, style

HERE = Path(__file__).resolve().parent
REPO_URL = "https://github.com/[handle]/statcast-pipeline"   # set to your repo
MIN_CELL_TAKES = 25          # hide heatmap cells with too few pitches to trust
MIN_COUNT_CELL_TAKES = 10    # one count is a smaller slice, so allow thinner cells
MIN_UMP_CELL_TAKES = 20      # per-umpire map uses 4-inch x 20%-of-zone cells


def data_dir() -> Path:
    if os.environ.get("DASHBOARD_DATA"):
        return Path(os.environ["DASHBOARD_DATA"])
    real = HERE / "data"
    return real if (real / "health.json").exists() else HERE / "data_sample"


@st.cache_data
def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(data_dir() / f"{name}.parquet")


@st.cache_data
def health() -> dict:
    return json.loads((data_dir() / "health.json").read_text())


def show(chart) -> None:
    st.altair_chart(style(chart), theme=None, width="content")


def pct(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Rates as percent numbers, so tables show one consistent decimal ("92.8%")."""
    return df.assign(**{c: df[c] * 100 for c in cols})


PCT = "%.1f%%"


def table_view(df: pd.DataFrame, label: str = "Show data as a table") -> None:
    with st.expander(label):
        st.dataframe(df, hide_index=True, width="stretch")


def season_picker(key: str, seasons: list[int]) -> int:
    return st.segmented_control("Season", options=sorted(seasons, reverse=True), default=max(seasons),
                                key=key) or max(seasons)


def coarsen(grid: pd.DataFrame) -> pd.DataFrame:
    """Merge 2-inch x 10% cells into 4-inch x 20% cells (one umpire has too few takes for the fine grid)."""
    # Vertical cells 0-0.2, ..., 0.8-1.0 line up with the zone's bottom and top.
    g = grid.assign(x_in=(grid["x_in"] + 20) // 4 * 4 - 18,
                    z_norm=(grid["z_norm"] // 0.2 * 0.2 + 0.1).round(2))
    g = g.groupby(["x_in", "z_norm"], as_index=False)[["takes", "called_strikes"]].sum()
    g["called_strike_rate"] = g["called_strikes"] / g["takes"]
    return g


def combine_counts(league_grid: pd.DataFrame, counts: list[str]) -> pd.DataFrame:
    """Pool several ball-strike counts into one heatmap layer."""
    g = (league_grid[league_grid["count_state"].isin(counts)]
         .groupby(["x_in", "z_norm"], as_index=False)[["takes", "called_strikes"]].sum())
    g["called_strike_rate"] = g["called_strikes"] / g["takes"]
    return g[g["takes"] >= MIN_COUNT_CELL_TAKES]


# --- pages -------------------------------------------------------------------

def two_strike_page() -> None:
    st.title("Umpires shrink the strike zone with two strikes")
    st.caption("Every taken pitch, regular season, scored against the rulebook zone (dashed).")

    by_count = load("accuracy_by_count")
    grid = load("zone_grid")
    season = season_picker("season_two_strike", by_count["season"].unique().tolist())
    bc = by_count[by_count["season"] == season]

    total = bc["called_pitches"].sum()
    acc = (bc["accuracy"] * bc["called_pitches"]).sum() / total
    rate = bc.set_index("count_state")["in_zone_called_ball_rate"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Called-pitch accuracy", f"{acc:.1%}", help="Share of taken pitches called correctly")
    c2.metric("Called pitches", f"{total:,}")
    c3.metric("In-zone takes called balls at 0-2", f"{rate.get('0-2', float('nan')):.0%}",
              delta=f"{(rate.get('0-2', 0) - rate.get('0-0', 0)) * 100:+.0f} pts vs. 0-0", delta_color="off")

    league = grid[(grid["season"] == season) & (grid["scope"] == "league")]
    first = combine_counts(league, ["0-0"])
    two = combine_counts(league, ["0-2", "1-2", "2-2", "3-2"])
    st.subheader("Where pitches get called strikes: first pitch vs. two strikes")
    show(alt.hconcat(called_strike_heatmap(first, "0-0 count"),
                     called_strike_heatmap(two, "Two strikes (0-2, 1-2, 2-2, 3-2)", show_y=False))
         .resolve_scale(color="shared"))
    st.caption("Darker = more often called a strike. With two strikes the dark area pulls inside the "
               f"rulebook zone. Cells with fewer than {MIN_COUNT_CELL_TAKES} takes are hidden.")

    st.subheader("How often a strike in the zone is called a ball, by count")
    show(count_bars(bc, "in_zone_called_ball_rate", None, "In-zone takes called balls"))
    st.caption("Takes inside the rulebook zone only. Part of the two-strike jump is selection: with two "
               "strikes batters swing at clear strikes, so the strikes they take are closer to the edge.")
    table_view(bc.sort_values(["balls", "strikes"])[
        ["count_state", "called_pitches", "accuracy", "in_zone_called_ball_rate",
         "out_of_zone_called_strike_rate", "edge_accuracy"]])


def umpires_page() -> None:
    st.title("Home-plate umpires")
    ua = load("umpire_accuracy")
    grid = load("zone_grid")
    season = season_picker("season_umps", ua["season"].unique().tolist())
    min_calls = st.slider("Minimum called pitches", 0, 4000, 2000 if ua["called_pitches"].max() > 2000 else 0,
                          step=250)

    board = ua[(ua["season"] == season) & (ua["called_pitches"] >= min_calls)].sort_values(
        "accuracy", ascending=False)
    if board.empty:
        st.info("No umpires meet that minimum. Lower the slider.")
        return

    st.subheader(f"Accuracy leaderboard, {season}")
    st.dataframe(
        pct(board, ["accuracy", "accuracy_vs_league", "edge_accuracy", "two_strike_accuracy",
                    "three_ball_accuracy"])[
              ["umpire_name", "games", "called_pitches", "accuracy", "accuracy_vs_league",
               "missed_calls_per_game", "edge_accuracy", "two_strike_accuracy", "three_ball_accuracy"]],
        hide_index=True, width="stretch",
        column_config={
            "umpire_name": "Umpire",
            "games": st.column_config.NumberColumn("Games"),
            "called_pitches": st.column_config.NumberColumn("Called pitches", format="localized"),
            "accuracy": st.column_config.NumberColumn("Accuracy", format=PCT),
            "accuracy_vs_league": st.column_config.NumberColumn("vs. league (pts)", format="%+.2f"),
            "missed_calls_per_game": st.column_config.NumberColumn("Misses / game", format="%.1f"),
            "edge_accuracy": st.column_config.NumberColumn("Edge accuracy", format=PCT),
            "two_strike_accuracy": st.column_config.NumberColumn("2-strike accuracy", format=PCT),
            "three_ball_accuracy": st.column_config.NumberColumn("3-ball accuracy", format=PCT),
        },
    )

    st.subheader("One umpire's zone vs. the league")
    name = st.selectbox("Umpire", board["umpire_name"].tolist())
    row = board[board["umpire_name"] == name].iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Accuracy", f"{row['accuracy']:.1%}", delta=f"{row['accuracy_vs_league'] * 100:+.1f} pts vs. league")
    c2.metric("Missed calls per game", f"{row['missed_calls_per_game']:.1f}")
    c3.metric("Edge-pitch accuracy", f"{row['edge_accuracy']:.1%}")

    g = grid[grid["season"] == season]
    ump = coarsen(g[(g["scope"] == "umpire") & (g["umpire_id"] == row["umpire_id"])])
    ump = ump[ump["takes"] >= MIN_UMP_CELL_TAKES]
    lg = coarsen(g[(g["scope"] == "league") & (g["count_state"] == "all")])[["x_in", "z_norm", "called_strike_rate"]]
    diff = ump.merge(lg.rename(columns={"called_strike_rate": "league_rate"}), on=["x_in", "z_norm"])
    diff["diff"] = diff["called_strike_rate"] - diff["league_rate"]
    show(difference_heatmap(diff, f"{name}: called-strike rate minus league, {season}"))
    st.caption("Blue = calls more strikes than the league there; red = fewer; gray = same as league. "
               f"4-inch cells; those with fewer than {MIN_UMP_CELL_TAKES} takes by this umpire are hidden.")
    table_view(diff[["x_in", "z_norm", "takes", "called_strike_rate", "league_rate", "diff"]])


def arsenal_page() -> None:
    st.title("Pitcher arsenals")
    ars = load("pitcher_arsenal")
    season = season_picker("season_arsenal", ars["season"].unique().tolist())
    s = ars[ars["season"] == season]
    totals = s.groupby(["pitcher_id", "pitcher_name"], as_index=False)["pitches"].sum().sort_values(
        "pitches", ascending=False)
    name = st.selectbox("Pitcher (most pitches first; type to search)", totals["pitcher_name"].tolist())
    mine = s[s["pitcher_name"] == name].sort_values("pitches", ascending=False)

    left, right = st.columns([3, 2])
    with left:
        show(movement_plot(mine, f"{name}: average movement by pitch, {season}").properties(width=430))
        st.caption("Catcher's view. Dot size = how often the pitch is thrown.")
    with right:
        st.dataframe(
            pct(mine, ["usage_rate", "whiff_rate", "csw_rate"])[
                ["pitch_name", "usage_rate", "avg_velocity_mph", "whiff_rate", "csw_rate", "run_value_per_100"]],
            hide_index=True, width="stretch",
            column_config={
                "pitch_name": "Pitch",
                "usage_rate": st.column_config.NumberColumn("Usage", format=PCT),
                "avg_velocity_mph": st.column_config.NumberColumn("mph", format="%.1f"),
                "whiff_rate": st.column_config.NumberColumn("Whiff", format=PCT),
                "csw_rate": st.column_config.NumberColumn("CSW", format=PCT),
                "run_value_per_100": st.column_config.NumberColumn("RV/100", format="%.2f",
                                                                   help="Runs saved per 100 pitches"),
            },
        )

    st.subheader("Which pitches move least predictably?")
    mc = load("movement_consistency")
    mcs = mc[mc["season"] == season]
    show(spread_bars(mcs, f"Average pitch-to-pitch movement spread, {season}").properties(width=560))
    st.caption("For each pitcher throwing a pitch at least 50 times, how much its break varies from one "
               "pitch to the next; averaged across pitchers. The knuckleball stands apart.")
    table_view(mcs[["pitch_name", "pitchers", "pitches", "avg_velocity_mph", "avg_sd_horizontal_break_in",
                    "avg_sd_induced_vertical_break_in", "movement_spread_in"]])


def health_page() -> None:
    st.title("Pipeline health")
    h = health()
    dbt = h.get("dbt") or {}
    counts = dbt.get("status_counts", {})
    failed = counts.get("error", 0) + counts.get("fail", 0)
    warned = counts.get("warn", 0)
    passed = counts.get("pass", 0) + counts.get("success", 0)

    c1, c2, c3 = st.columns(3)
    c1.metric("Pitches in warehouse", f"{h['rows']['core.fct_pitches']:,}")
    c2.metric("Last data extracted (UTC)", (h.get("last_extracted_at") or "n/a")[:16])
    c3.metric("Dashboard data published (UTC)", h["published_at"][:16].replace("T", " "))

    if failed:
        st.error(f"✖ Data checks: {failed} failed, {warned} warned, {passed} passed", icon="🚨")
    elif warned:
        st.warning(f"⚠ Data checks: {warned} warned, {passed} passed, 0 failed")
    else:
        st.success(f"✔ Data checks: all {passed} passed")
    for f in dbt.get("flagged", []):
        st.write(f"- `{f['node']}`: {f['status']} ({f.get('failures') or 0} rows)")

    st.subheader("Coverage by season")
    seasons = pd.DataFrame(h["seasons"])
    st.dataframe(seasons, hide_index=True, width="stretch", column_config={
        "season": st.column_config.NumberColumn("Season", format="%d"),
        "regular_season_games": "Regular-season games",
        "postseason_games": "Postseason games",
        "spring_games": "Spring games",
        "pitches": st.column_config.NumberColumn("Pitches", format="localized"),
        "first_game": "First game", "last_game": "Last game",
        "regular_games_without_umpire": "Regular games w/o umpire",
    })
    st.caption("A full regular season is 2,430 games.")

    st.subheader("Rows by table")
    st.dataframe(pd.DataFrame(list(h["rows"].items()), columns=["Table", "Rows"]), hide_index=True,
                 column_config={"Rows": st.column_config.NumberColumn("Rows", format="localized")})
    st.markdown(f"Source code, tests and data model: [{REPO_URL}]({REPO_URL})")
