import { useEffect, useRef } from "react";
import Plotly from "plotly.js-basic-dist-min";
import { historical, telemetry } from "../../data/mockData";

function Plot({ data, layout, config, className = "", style }) {
  const container = useRef(null);

  useEffect(() => {
    const node = container.current;
    Plotly.react(node, data, layout, config);
    const resizeObserver = new ResizeObserver(() => Plotly.Plots.resize(node));
    resizeObserver.observe(node);
    return () => {
      resizeObserver.disconnect();
      Plotly.purge(node);
    };
  }, [data, layout, config]);

  return <div ref={container} className={className} style={style} />;
}

const colors = {
  red: "#d6574e",
  blue: "#4b84d1",
  green: "#1d7b50",
  lime: "#83a841",
  purple: "#8b67c6",
  amber: "#e8982f",
};

export const plotConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};

const baseLayout = {
  autosize: true,
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { family: "DM Sans, sans-serif", color: "#69756d", size: 10 },
  hoverlabel: { bgcolor: "#173d2b", bordercolor: "#173d2b", font: { color: "#fff", family: "DM Sans, sans-serif" } },
  margin: { l: 44, r: 16, t: 12, b: 34 },
  legend: { orientation: "h", x: 0, y: 1.14, font: { size: 10 } },
  xaxis: { gridcolor: "#edf0ec", zeroline: false, linecolor: "#e1e7df", tickfont: { size: 9 } },
  yaxis: { gridcolor: "#edf0ec", zeroline: false, linecolor: "#e1e7df", tickfont: { size: 9 } },
};

export function SparklineChart({ values, color = "green", className = "metric-spark" }) {
  const resolved = colors[color] ?? color;
  return (
    <div className={className} aria-hidden="true">
      <Plot
        data={[{ y: values, type: "scatter", mode: "lines", line: { color: resolved, width: 2, shape: "spline" }, fill: "tozeroy", fillcolor: `${resolved}14`, hoverinfo: "skip" }]}
        layout={{ autosize: true, margin: { l: 0, r: 0, t: 2, b: 0 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", xaxis: { visible: false, fixedrange: true }, yaxis: { visible: false, fixedrange: true } }}
        config={{ ...plotConfig, staticPlot: true }}
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}

export function TelemetryChart({ range = "24h" }) {
  const count = range === "6h" ? 6 : range === "7d" ? 24 : 24;
  const x = telemetry.time.slice(-count);
  const traces = [
    { name: "Temperature", values: telemetry.temperature, color: colors.blue, unit: "°C" },
    { name: "Moisture", values: telemetry.moisture, color: "#1fae78", unit: "%" },
    { name: "CO₂", values: telemetry.co2.map((value) => value * 15), color: colors.purple, unit: "%" },
  ].map((item) => ({
    x,
    y: item.values.slice(-count),
    name: item.name,
    type: "scatter",
    mode: "lines",
    line: { color: item.color, width: 2, shape: "spline" },
    hovertemplate: `%{y:.1f}${item.unit}<extra>${item.name}</extra>`,
  }));

  return <Plot className="chart" data={traces} layout={{ ...baseLayout, hovermode: "x unified" }} config={plotConfig} style={{ width: "100%", height: "260px" }} />;
}

export function PhaseHistoryChart() {
  const stageColors = ["#ef8c35", "#ef8c35", "#19a76f", "#19a76f", "#4b84d1", "#83a841"];
  return (
    <Plot
      className="chart"
      data={[{
        x: historical.dates,
        y: historical.temperature,
        type: "scatter",
        mode: "lines",
        line: { color: "#173d2b", width: 2, shape: "spline" },
        fill: "tozeroy",
        fillcolor: "rgba(29,123,80,.12)",
        marker: { color: stageColors },
        name: "Temperature",
        hovertemplate: "%{x}<br>%{y:.1f}°C<extra></extra>",
      }]}
      layout={{
        ...baseLayout,
        showlegend: false,
        shapes: [
          { type: "rect", xref: "x", yref: "paper", x0: "Day 1", x1: "Day 7", y0: 0, y1: 1, fillcolor: "rgba(232,152,47,.12)", line: { width: 0 } },
          { type: "rect", xref: "x", yref: "paper", x0: "Day 8", x1: "Day 26", y0: 0, y1: 1, fillcolor: "rgba(29,123,80,.09)", line: { width: 0 } },
          { type: "line", xref: "paper", x0: 0, x1: 1, y0: 55, y1: 55, line: { color: colors.red, dash: "dot", width: 1 } },
        ],
        annotations: [{ xref: "paper", yref: "y", x: 0.01, y: 55, text: "Target threshold", showarrow: false, yshift: 9, font: { color: colors.red, size: 9 } }],
      }}
      config={plotConfig}
      style={{ width: "100%", height: "260px" }}
    />
  );
}

export function HealthChart() {
  return (
    <Plot
      className="chart"
      data={[{
        x: historical.dates,
        y: historical.health,
        type: "scatter",
        mode: "lines",
        line: { color: colors.green, width: 2.5, shape: "spline" },
        fill: "tozeroy",
        fillcolor: "rgba(29,123,80,.1)",
        hovertemplate: "%{x}<br>Health %{y:.0f}/100<extra></extra>",
      }]}
      layout={{ ...baseLayout, showlegend: false, yaxis: { ...baseLayout.yaxis, range: [40, 100] } }}
      config={plotConfig}
      style={{ width: "100%", height: "260px" }}
    />
  );
}
