"""Chart builders (Altair) with one consistent visual system.

Palette and chrome follow a validated reference palette: one sequential blue
ramp for magnitude, a blue <-> red diverging pair around a neutral gray for
"vs. league", thin marks, recessive gridlines, and a tooltip on every mark.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

# --- palette (light theme; the app is pinned to light in .streamlit/config.toml) ---
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIVERGING = ["#c53b3a", "#e34948", "#f0a3a2", "#f0efec", "#9ec5f4", "#2a78d6", "#1c5cab"]
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

# Rulebook zone (no ball-radius padding) in the heatmap's coordinates.
ZONE = pd.DataFrame({"x0": [-8.5], "x1": [8.5], "z0": [0.0], "z1": [1.0]})


def style(chart: alt.Chart) -> alt.Chart:
    return (
        chart.properties(padding={"top": 14, "left": 6, "right": 6, "bottom": 6})
        .configure(font=FONT, background=SURFACE)
        .configure_view(stroke=None)
        .configure_axis(labelColor=MUTED, titleColor=INK_2, gridColor=GRID, domainColor=BASELINE,
                        tickColor=BASELINE, labelFontSize=11, titleFontSize=12, titleFontWeight="normal")
        .configure_legend(labelColor=INK_2, titleColor=INK_2, labelFontSize=11, titleFontSize=11,
                          titleFontWeight="normal")
        .configure_title(color=INK, fontSize=13, fontWeight="normal", anchor="start")
    )


def _cells(grid: pd.DataFrame, cell_w: float = 2, cell_h: float = 0.1) -> pd.DataFrame:
    g = grid.copy()
    g["x0"], g["x1"] = g["x_in"] - cell_w / 2, g["x_in"] + cell_w / 2
    g["z0"], g["z1"] = g["z_norm"] - cell_h / 2, g["z_norm"] + cell_h / 2
    return g


def _zone_axes(title: str, show_y: bool = True):
    x = alt.X("x0:Q", scale=alt.Scale(domain=[-20, 20], nice=False),
              axis=alt.Axis(title="Horizontal (in, catcher's view)", values=[-15, -10, -5, 0, 5, 10, 15],
                            grid=False))
    y = alt.Y("z0:Q", scale=alt.Scale(domain=[-0.5, 1.5], nice=False),
              axis=alt.Axis(title="Height (share of batter's zone)" if show_y else None,
                            values=[0, 0.5, 1], format="%", grid=False, labels=show_y))
    return x, y


def _zone_outline() -> alt.Chart:
    return alt.Chart(ZONE).mark_rect(fill=None, stroke=INK, strokeWidth=1.5, strokeDash=[4, 3]).encode(
        x="x0:Q", x2="x1:Q", y="z0:Q", y2="z1:Q")


def called_strike_heatmap(grid: pd.DataFrame, title: str, show_y: bool = True,
                          width: int = 290, height: int = 320) -> alt.LayerChart:
    """Called-strike probability per cell (sequential blue), with the rulebook zone dashed."""
    x, y = _zone_axes(title, show_y)
    cells = alt.Chart(_cells(grid)).mark_rect(stroke=SURFACE, strokeWidth=1).encode(
        x=x, x2="x1:Q", y=y, y2="z1:Q",
        color=alt.Color("called_strike_rate:Q", title="Called strike rate",
                        scale=alt.Scale(domain=[0, 1], range=SEQ_BLUE, interpolate="rgb"),
                        legend=alt.Legend(format="%", orient="bottom", gradientLength=220)),
        tooltip=[alt.Tooltip("x_in:Q", title="Horizontal (in)"),
                 alt.Tooltip("z_norm:Q", title="Height (zone share)", format=".0%"),
                 alt.Tooltip("called_strike_rate:Q", title="Called strike rate", format=".1%"),
                 alt.Tooltip("takes:Q", title="Takes", format=",")],
    )
    return alt.layer(cells, _zone_outline()).properties(title=title, width=width, height=height)


def difference_heatmap(diff: pd.DataFrame, title: str, cell_w: float = 4, cell_h: float = 0.2) -> alt.LayerChart:
    """Umpire minus league called-strike rate per cell (diverging, gray = same as league)."""
    x, y = _zone_axes(title)
    cells = alt.Chart(_cells(diff, cell_w, cell_h)).mark_rect(stroke=SURFACE, strokeWidth=1).encode(
        x=x, x2="x1:Q", y=y, y2="z1:Q",
        color=alt.Color("diff:Q", title="Called strikes vs. league (points)",
                        scale=alt.Scale(domain=[-0.3, 0.3], range=DIVERGING, clamp=True, interpolate="rgb"),
                        legend=alt.Legend(format="+.0%", orient="bottom", gradientLength=220)),
        tooltip=[alt.Tooltip("x_in:Q", title="Horizontal (in)"),
                 alt.Tooltip("z_norm:Q", title="Height (zone share)", format=".0%"),
                 alt.Tooltip("called_strike_rate:Q", title="This umpire", format=".1%"),
                 alt.Tooltip("league_rate:Q", title="League", format=".1%"),
                 alt.Tooltip("diff:Q", title="Difference", format="+.1%"),
                 alt.Tooltip("takes:Q", title="Takes", format=",")],
    )
    return alt.layer(cells, _zone_outline()).properties(title=title, width=330, height=360)


def count_bars(df: pd.DataFrame, field: str, title: str | None, axis_title: str) -> alt.Chart:
    """One bar per ball-strike count, in count order; values labeled on the bars."""
    order = df.sort_values(["balls", "strikes"])["count_state"].tolist()
    base = alt.Chart(df).encode(
        x=alt.X("count_state:N", sort=order, title="Count (balls-strikes)", axis=alt.Axis(labelAngle=0)),
        y=alt.Y(f"{field}:Q", title=axis_title, axis=alt.Axis(format="%", tickCount=5)),
        tooltip=[alt.Tooltip("count_state:N", title="Count"),
                 alt.Tooltip(f"{field}:Q", title=axis_title, format=".1%"),
                 alt.Tooltip("called_pitches:Q", title="Called pitches", format=",")],
    )
    bars = base.mark_bar(color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=26)
    labels = base.mark_text(dy=-7, color=INK_2, fontSize=11).encode(text=alt.Text(f"{field}:Q", format=".0%"))
    chart = alt.layer(bars, labels).properties(height=260, width=560)
    return chart.properties(title=title) if title else chart


def movement_plot(arsenal: pd.DataFrame, title: str) -> alt.LayerChart:
    """Average movement per pitch type: one hue, each dot labeled with its pitch name."""
    base = alt.Chart(arsenal).encode(
        x=alt.X("avg_horizontal_break_in:Q", title="Horizontal break (in)",
                scale=alt.Scale(domain=[-22, 22])),
        y=alt.Y("avg_induced_vertical_break_in:Q", title="Induced vertical break (in)",
                scale=alt.Scale(domain=[-18, 22])),
        tooltip=[alt.Tooltip("pitch_name:N", title="Pitch"),
                 alt.Tooltip("usage_rate:Q", title="Usage", format=".1%"),
                 alt.Tooltip("avg_velocity_mph:Q", title="Velocity (mph)"),
                 alt.Tooltip("avg_horizontal_break_in:Q", title="Horizontal break (in)"),
                 alt.Tooltip("avg_induced_vertical_break_in:Q", title="Vertical break (in)"),
                 alt.Tooltip("whiff_rate:Q", title="Whiff rate", format=".1%")],
    )
    zero = pd.DataFrame({"v": [0]})
    rule_x = alt.Chart(zero).mark_rule(color=BASELINE).encode(x="v:Q")
    rule_y = alt.Chart(zero).mark_rule(color=BASELINE).encode(y="v:Q")
    dots = base.mark_circle(color=BLUE, opacity=0.9, stroke=SURFACE, strokeWidth=2).encode(
        size=alt.Size("usage_rate:Q", title="Usage", scale=alt.Scale(range=[80, 900]),
                      legend=alt.Legend(format=".0%", orient="bottom")))
    labels = base.mark_text(dx=18, align="left", color=INK_2, fontSize=11).encode(text="pitch_name:N")
    return alt.layer(rule_x, rule_y, dots, labels).properties(title=title, height=380)


def spread_bars(df: pd.DataFrame, title: str) -> alt.Chart:
    """Movement spread by pitch type, sorted, biggest first."""
    base = alt.Chart(df).encode(
        y=alt.Y("pitch_name:N", sort="-x", title=None),
        x=alt.X("movement_spread_in:Q", title="Typical pitch-to-pitch movement spread (in)"),
        tooltip=[alt.Tooltip("pitch_name:N", title="Pitch"),
                 alt.Tooltip("movement_spread_in:Q", title="Spread (in)"),
                 alt.Tooltip("pitchers:Q", title="Pitchers"),
                 alt.Tooltip("pitches:Q", title="Pitches", format=",")],
    )
    bars = base.mark_bar(color=BLUE, cornerRadiusTopRight=4, cornerRadiusBottomRight=4, size=16)
    labels = base.mark_text(dx=6, align="left", color=INK_2, fontSize=11).encode(
        text=alt.Text("movement_spread_in:Q", format=".1f"))
    return alt.layer(bars, labels).properties(title=title, height=alt.Step(26))
