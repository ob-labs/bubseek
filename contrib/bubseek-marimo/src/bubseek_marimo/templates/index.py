"""Bubseek Insights index — open dashboard or browse notebooks."""

# marimo.App (for directory scanner)
import marimo as mo

app = mo.App()


@app.cell
def _():
    from pathlib import Path

    import marimo as mo

    insights_dir = Path(__file__).resolve().parent
    return (insights_dir, mo)


@app.cell
def _(insights_dir, mo):
    notebooks = sorted(
        [path for path in insights_dir.glob("*.py") if path.name not in {"dashboard.py", "index.py"}],
        key=lambda path: path.stat().st_mtime,
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
        lines.extend(f"- [{path.stem}](/?file={path.name})" for path in notebooks)
        page = mo.md("\n".join(lines))
    else:
        page = mo.md(
            "# Bubseek Insights\n\n"
            "- [Open dashboard](/?file=dashboard.py)\n\n"
            "- [Open starter visualization example](/?file=example_visualization.py)\n\n"
            "No insight notebooks yet. Ask Bub in the dashboard to generate one."
        )
    page  # noqa: B018
    return (page,)


if __name__ == "__main__":
    app.run()
