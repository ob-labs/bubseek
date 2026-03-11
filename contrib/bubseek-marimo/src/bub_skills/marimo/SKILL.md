---
name: marimo
description: |
  Marimo channel and insight skill. When $marimo in context, return text for gateway chat.
  For data analysis and insights, output marimo .py notebooks; create index for charts.
metadata:
  channel: marimo
---

# Marimo Skill

bubseek uses marimo for **data insights and charts** — single Python file format, cell-based interaction, and an index of generated visualizations.

## When $marimo in Message Context (Gateway Chat)

Return your response as plain text. The framework delivers it to the WebSocket dashboard.

## When Producing Data Insights or Charts

**Output as marimo notebooks** — single `.py` files in the workspace. This is central to bubseek's insight direction.

### Output Location

- Canonical runtime directory: `{workspace}/insights/`
- Do not write runtime notebooks into the installed package directory or `site-packages`
- Each insight: `insights/{topic}_{timestamp}.py` or `insights/{name}.py`
- Index: `insights/index.py` — aggregates links to all generated charts/notebooks

### marimo Notebook Format

Follow [marimo-notebook](https://github.com/marimo-team/skills/tree/main/skills/marimo-notebook) conventions:

```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "pandas", "matplotlib"]
# ///

import marimo as mo
app = marimo.App(width="medium")

@app.cell
def _():
    import pandas as pd
    import matplotlib.pyplot as plt
    return pd, plt

@app.cell
def _(mo):
    mo.md("# Insight: Sales Trend")
    return

@app.cell
def _(pd, plt):
    df = pd.DataFrame(...)  # your data
    fig, ax = plt.subplots()
    ax.plot(df["x"], df["y"])
    fig  # final expression renders
    return

if __name__ == "__main__":
    app.run()
```

### Key Conventions

- **Cell structure**: `@app.cell` decorator; function inputs/outputs = cell dependencies
- **Final expression**: Only the last expression of a cell renders; no indented display
- **Reactivity**: Variables between cells define reactivity; avoid mutating across cells
- **PEP 723**: Add `# /// script` block with dependencies at top
- **Scanner compatibility**: notebooks opened from a marimo directory must contain the literal markers `import marimo` and `marimo.App`
- **Run**: `uv run marimo run <notebook.py>` for interactive; `uv run <notebook.py>` for script mode

### Index (Native marimo)

When the Marimo channel starts, it runs `marimo run <workspace>/insights`. The **dashboard** (click "dashboard" in the gallery) has:

- **Chat** — native marimo form widgets posting to `/api/chat`
- **Index** — native marimo links to dashboard and generated notebooks
- **Starter example** — `example_visualization.py` to verify scanner compatibility and native widgets

### Cell Interaction for Exploration

- Use `mo.ui.slider()`, `mo.ui.dropdown()` etc. for interactive exploration
- Data source can switch via `mo.app_meta().mode == "script"` (synthetic in script, widget in interactive)
- See marimo-team/skills marimo-notebook for full patterns

## Combine with Other Marimo Skills

When building insight notebooks, **combine with these bundled marimo skills** as needed:

| Skill | Use when |
| --- | --- |
| **marimo-notebook** | Notebook format, cell structure, PEP 723, reactivity, `marimo check` |
| **anywidget** | Custom interactive widgets; wrap with `mo.ui.anywidget(Widget())` |
| **add-molab-badge** | Deploy to molab; add "Open in molab" badge |
| **implement-paper** | Implementing algorithms or visualizations from papers |
| **marimo-batch** | Batch processing over datasets |
| **wasm-compatibility** | Notebooks that run in WASM / browser constraints |

Always follow **marimo-notebook** for structure. Add **anywidget** when you need custom UI. Use **add-molab-badge** for shareable deployments.

## Channel Dashboard

Native marimo app (not iframe). Chat + index in one view, with all runtime notebooks generated into `<workspace>/insights`.
