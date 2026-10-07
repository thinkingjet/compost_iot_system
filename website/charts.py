"""Charts for the website, drawn as inline SVG when the site is built.

There is no chart library and no JavaScript: a 30-day chart is about 3.5 KB of
markup that appears with the rest of the HTML. Plotly, which the dashboard
uses, would add roughly 1.5 MB (gzipped) of script that has to download and
run before anything is drawn. Hovering a point shows its value through the
browser's native SVG <title> tooltip.

Colours live in assets/site.css (the .chart* classes), not here, so the
charts follow the site's theme.
"""
from markupsafe import Markup, escape

# Space around the plot area, in viewBox units, for the axis labels.
_LEFT, _TOP, _RIGHT, _BOTTOM = 44, 14, 16, 36


def _day_label(day):
    return f"{day.day} {day:%b}"


def _num(value):
    return f"{value:.1f}".rstrip("0").rstrip(".")


def line_chart(days, values, *, series, unit, point_unit, y_min, y_max, y_ticks, label,
               threshold=None, band=None, width=600, height=180):
    """A daily line chart.

    days      list of datetime.date, oldest first
    values    one number per day; None leaves a gap
    series    CSS modifier for the line colour ("temp" or "moist")
    unit      suffix for the axis labels ("°"); point_unit for tooltips ("°C")
    threshold (value, text) for a dashed reference line
    band      (low, high, text) for a shaded target range
    """
    def x(i):
        return i * width / max(len(days) - 1, 1)

    def y(v):
        return height - (v - y_min) / (y_max - y_min) * height

    parts = [f'<g transform="translate({_LEFT},{_TOP})">']
    if band:
        low, high, text = band
        parts.append(f'<rect class="chart__band" x="0" y="{y(high):.1f}" width="{width}" height="{y(low) - y(high):.1f}"/>')
        parts.append(f'<text class="chart__band-label" x="{width}" y="{y(high) - 6:.1f}" text-anchor="end">{escape(text)}</text>')
    for tick in y_ticks:
        parts.append(f'<line class="chart__grid" x1="0" y1="{y(tick):.1f}" x2="{width}" y2="{y(tick):.1f}"/>')
        parts.append(f'<text x="-10" y="{y(tick) + 4:.1f}" text-anchor="end">{_num(tick)}{escape(unit)}</text>')
    parts.append(f'<line class="chart__axis" x1="0" y1="{height}" x2="{width}" y2="{height}"/>')
    if threshold:
        value, text = threshold
        parts.append(f'<line class="chart__threshold" x1="0" y1="{y(value):.1f}" x2="{width}" y2="{y(value):.1f}"/>')
        parts.append(f'<text class="chart__threshold-label" x="{width}" y="{y(value) - 7:.1f}" text-anchor="end">{escape(text)}</text>')

    # One polyline per unbroken run of values, so a missing day is a gap.
    run = []
    for i, v in enumerate(values + [None]):
        if v is None:
            if len(run) > 1:
                parts.append(f'<polyline class="chart__line chart__line--{series}" points="{" ".join(run)}"/>')
            run = []
        else:
            run.append(f"{x(i):.1f},{y(v):.1f}")

    parts.append(f'<g class="chart__pts chart__pts--{series}">')
    for i, (day, v) in enumerate(zip(days, values)):
        if v is not None:
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="6"><title>{_day_label(day)}: {_num(v)} {escape(point_unit)}</title></circle>')
    parts.append("</g>")

    middle = len(days) // 2
    parts.append(f'<text x="0" y="{height + 24}">{_day_label(days[0])}</text>')
    parts.append(f'<text x="{x(middle):.1f}" y="{height + 24}" text-anchor="middle">{_day_label(days[middle])}</text>')
    parts.append(f'<text x="{width}" y="{height + 24}" text-anchor="end">{_day_label(days[-1])}</text>')
    parts.append("</g>")

    view_w, view_h = _LEFT + width + _RIGHT, _TOP + height + _BOTTOM
    return Markup(
        f'<svg class="chart" viewBox="0 0 {view_w} {view_h}" role="img" aria-label="{escape(label)}">'
        + "".join(parts) + "</svg>"
    )


def sparkline(values, *, y_min, y_max, reference=None, width=280, height=64):
    """A small trend line with no axes. `reference` draws a dashed level."""
    def y(v):
        return height - (v - y_min) / (y_max - y_min) * height

    step = width / max(len(values) - 1, 1)
    points = " ".join(f"{i * step:.1f},{y(v):.1f}" for i, v in enumerate(values))
    ref = ""
    if reference is not None:
        ref = f'<line class="spark__ref" x1="0" y1="{y(reference):.1f}" x2="{width}" y2="{y(reference):.1f}"/>'
    return Markup(
        f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        f'{ref}<polyline class="spark__line" points="{points}"/></svg>'
    )


def bar(fraction):
    """A horizontal bar filled to `fraction` (0 to 1) of its width."""
    filled = max(0.0, min(1.0, fraction)) * 100
    return Markup(
        '<svg class="bar" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
        f'<rect class="bar__track" width="100" height="8" rx="4"/><rect class="bar__fill" width="{filled:.1f}" height="8" rx="4"/></svg>'
    )
