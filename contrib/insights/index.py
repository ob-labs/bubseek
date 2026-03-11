"""Bubseek Insights index — open dashboard or browse notebooks."""
# marimo.App (for directory scanner)
import marimo as mo

app = mo.App()


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

    insights_dir = Path('/home/shangzhuoran.szr/oceanbase/bubseek/contrib/insights')
    return insights_dir, mo


@app.cell
def _(insights_dir, mo):
    notebooks = sorted(
        [p for p in insights_dir.glob("*.py") if p.name not in {"dashboard.py", "index.py"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if notebooks:
        lines = [
            "# Bubseek Insights",
            "",
            "- [Open dashboard](/?file=dashboard.py)",
            "- [Open starter visualization example](/?file=example_visualization.py)",
            "",
            "## Notebooks",
        ]
        lines.extend(f"- [{p.stem}](/?file={p.name})" for p in notebooks)
        page = mo.md("\n".join(lines))
    else:
        page = mo.md(
            "# Bubseek Insights\n\n"
            "- [Open dashboard](/?file=dashboard.py)\n\n"
            "- [Open starter visualization example](/?file=example_visualization.py)\n\n"
            "No insight notebooks yet. Ask Bub in the dashboard to generate one."
        )
    page
    return


if __name__ == "__main__":
    app.run()
