# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo"]
# ///

"""Example native marimo visualization for Bubseek."""
# marimo.App (for directory scanner)

import marimo as mo

app = mo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    data = [
        {"month": "Jan", "sales": 120, "cost": 75},
        {"month": "Feb", "sales": 145, "cost": 83},
        {"month": "Mar", "sales": 170, "cost": 91},
        {"month": "Apr", "sales": 160, "cost": 95},
        {"month": "May", "sales": 210, "cost": 108},
        {"month": "Jun", "sales": 235, "cost": 120},
    ]
    return (data, mo)


@app.cell
def _(data, mo):
    metric = mo.ui.dropdown(
        options={"Sales": "sales", "Cost": "cost"},
        value="Sales",
        label="Metric",
    )
    scale = mo.ui.slider(0.6, 1.6, value=1.0, step=0.1, label="Scale")
    controls = mo.hstack([metric, scale], widths=[0.5, 0.5], align="end")
    return (metric, scale, controls, mo)


@app.cell
def _(controls, mo):
    header = mo.vstack(
        [
            mo.md("# Example Visualization"),
            mo.md("A native marimo example using widgets, reactivity, markdown, and SVG rendering."),
            controls,
        ],
        gap=0.75,
    )
    header  # noqa: B018
    return (header,)


@app.cell
def _(data, metric, mo, scale):
    selected = metric.value
    factor = scale.value
    max_value = max(row[selected] for row in data) or 1

    bars = []
    y = 30
    for row in data:
        value = row[selected]
        width = int((value / max_value) * 280 * factor)
        bars.append(
            f"""
            <text x="10" y="{y}" font-size="13" fill="#334155">{row["month"]}</text>
            <rect x="72" y="{y - 14}" rx="6" ry="6" width="{width}" height="20" fill="#2563eb"></rect>
            <text x="{82 + width}" y="{y}" font-size="12" fill="#0f172a">{value}</text>
            """
        )
        y += 34

    svg = f"""
    <svg width="420" height="{y}" viewBox="0 0 420 {y}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8fafc"></rect>
      {"".join(bars)}
    </svg>
    """

    summary = mo.md(
        f"### Summary\n"
        f"- Selected metric: **{selected}**\n"
        f"- Latest value: **{data[-1][selected]}**\n"
        f"- Peak value: **{max_value}**"
    )
    chart = mo.Html(svg)
    content = mo.vstack([summary, chart], gap=0.75)
    content  # noqa: B018
    return (content,)


if __name__ == "__main__":
    app.run()
