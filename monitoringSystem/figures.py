import plotly.graph_objects as go

from data import HISTORICAL, TELEMETRY


COLORS = {
    "red": "#d6574e",
    "blue": "#4b84d1",
    "green": "#1d7b50",
    "lime": "#83a841",
    "purple": "#8b67c6",
    "amber": "#e8982f",
}

GRAPH_CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}


def _base_layout(height=260):
    return {
        "height": height,
        "autosize": True,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "DM Sans, sans-serif", "color": "#69756d", "size": 10},
        "hoverlabel": {"bgcolor": "#173d2b", "bordercolor": "#173d2b", "font": {"color": "#fff"}},
        "margin": {"l": 44, "r": 16, "t": 12, "b": 34},
        "legend": {"orientation": "h", "x": 0, "y": 1.14, "font": {"size": 10}},
        "xaxis": {"gridcolor": "#edf0ec", "zeroline": False, "linecolor": "#e1e7df", "tickfont": {"size": 9}},
        "yaxis": {"gridcolor": "#edf0ec", "zeroline": False, "linecolor": "#e1e7df", "tickfont": {"size": 9}},
    }


def sparkline(values, color="green", height=50):
    resolved = COLORS.get(color, color)
    red = int(resolved[1:3], 16)
    green = int(resolved[3:5], 16)
    blue = int(resolved[5:7], 16)
    soft_fill = f"rgba({red},{green},{blue},0.08)"

    figure = go.Figure(
        go.Scatter(
            y=values,
            mode="lines",
            line={"color": resolved, "width": 2, "shape": "spline"},
            fill="tozeroy",
            fillcolor=soft_fill,
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        height=height,
        autosize=True,
        margin={"l": 0, "r": 0, "t": 2, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True},
    )
    return figure


def telemetry_figure(hours=24):
    count = 6 if hours == 6 else 24
    x = TELEMETRY["time"][-count:]
    figure = go.Figure()
    traces = [
        ("Temperature", TELEMETRY["temperature"], COLORS["blue"], "°C"),
        ("Moisture", TELEMETRY["moisture"], "#1fae78", "%"),
        ("CO₂", [value * 15 for value in TELEMETRY["co2"]], COLORS["purple"], "%"),
    ]
    for name, values, color, unit in traces:
        figure.add_trace(go.Scatter(x=x, y=values[-count:], name=name, mode="lines", line={"color": color, "width": 2, "shape": "spline"}, hovertemplate=f"%{{y:.1f}}{unit}<extra>{name}</extra>"))
    figure.update_layout(**_base_layout(), hovermode="x unified")
    return figure


def phase_history_figure():
    figure = go.Figure(
        go.Scatter(
            x=HISTORICAL["dates"],
            y=HISTORICAL["temperature"],
            mode="lines",
            name="Temperature",
            line={"color": "#173d2b", "width": 2, "shape": "spline"},
            fill="tozeroy",
            fillcolor="rgba(29,123,80,.12)",
            hovertemplate="%{x}<br>%{y:.1f}°C<extra></extra>",
        )
    )
    layout = _base_layout()
    layout.update(
        showlegend=False,
        shapes=[
            {"type": "rect", "xref": "x", "yref": "paper", "x0": "Day 1", "x1": "Day 7", "y0": 0, "y1": 1, "fillcolor": "rgba(232,152,47,.12)", "line": {"width": 0}, "layer": "below"},
            {"type": "rect", "xref": "x", "yref": "paper", "x0": "Day 8", "x1": "Day 26", "y0": 0, "y1": 1, "fillcolor": "rgba(29,123,80,.09)", "line": {"width": 0}, "layer": "below"},
            {"type": "line", "xref": "paper", "x0": 0, "x1": 1, "y0": 55, "y1": 55, "line": {"color": COLORS["red"], "dash": "dot", "width": 1}},
        ],
        annotations=[{"xref": "paper", "yref": "y", "x": 0.01, "y": 55, "text": "Target threshold", "showarrow": False, "yshift": 9, "font": {"color": COLORS["red"], "size": 9}}],
    )
    figure.update_layout(**layout)
    return figure


def health_figure():
    figure = go.Figure(
        go.Scatter(
            x=HISTORICAL["dates"],
            y=HISTORICAL["health"],
            mode="lines",
            line={"color": COLORS["green"], "width": 2.5, "shape": "spline"},
            fill="tozeroy",
            fillcolor="rgba(29,123,80,.1)",
            hovertemplate="%{x}<br>Health %{y:.0f}/100<extra></extra>",
        )
    )
    figure.update_layout(**_base_layout(), showlegend=False)
    figure.update_yaxes(range=[40, 100])
    return figure
