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

Return your response as plain text. The framework persists it as chat events, and the dashboard syncs those events into interactive marimo cells.

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
app = mo.App(width="medium")

@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import matplotlib.pyplot as plt
    return (pd, plt, mo)

@app.cell
def _(mo):
    title = mo.md("# Insight: Sales Trend")
    title   # last expression = displayed output
    return (title,)

@app.cell
def _(mo, pd, plt):
    df = pd.DataFrame(...)  # your data
    fig, ax = plt.subplots()
    ax.plot(df["x"], df["y"])
    fig   # last expression renders
    return (fig,)

if __name__ == "__main__":
    app.run()
```

### Key Conventions

- **Cell structure**: `@app.cell` decorator; function inputs/outputs = cell dependencies
- **First cell must pass `mo`**: In the first cell, `import marimo as mo` and include `mo` in the return (e.g. `return (data, mo)`). Later cells that use `mo.md()`, `mo.ui.*` etc. must receive `mo` from a previous cell's return — module-level `mo` is not available inside cells
- **Display**: The last expression in a cell is what gets rendered. For UI cells, assign to a variable, put that variable as the last expression, then `return (variable,)` so other cells can depend on it. To avoid duplicate output, use a **single final layout cell** that assembles the whole page and is the only cell that displays (other cells only return, no trailing display expression)
- **Variable names**: Must be unique across all cells (no multiple-definitions). Repeated local temporaries such as `session`, `events`, `result`, `response`, `row`, `item` should usually be underscore-prefixed inside cells (e.g. `_session`, `_events`, `_result`, `_row`) so they do not collide across cells
- **No mid-cell return**: Do not use `return` for early exit inside a cell; use conditionals to assign a value, then a single `return (...)` at the end. Mid-cell returns can make the notebook fail to compile
- **Reactivity**: Variables between cells define reactivity; avoid mutating across cells
- **PEP 723**: Add `# /// script` block with dependencies at top (include `pyobvector` when using `mysql+oceanbase` / seekdb)
- **Scanner compatibility**: notebooks opened from a marimo directory must contain the literal markers `import marimo` and `marimo.App`
- **Directory mode**: Use `marimo run <directory> --watch` so newly generated notebooks in the folder are visible without restarting
- **Run**: `uv run marimo run <notebook.py>` for interactive; `uv run <notebook.py>` for script mode
- **Validation**: Before handing a notebook back, run `uv run <notebook.py>` or `uvx marimo check <notebook.py>` to catch AST/graph errors such as invalid returns or multiple definitions

### Index (Native marimo)

When the Marimo channel starts, it runs `marimo run <workspace>/insights`. The **dashboard** (click "dashboard" in the gallery) has:

- **Chat** — native marimo form widgets submitting turns to `/api/chat/submit`, then syncing events from `/api/chat/events`
- **Index** — native marimo links to dashboard and generated notebooks

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

Native marimo app (not iframe). Chat + index in one view, with all runtime notebooks generated into `<workspace>/insights`. The dashboard should treat agent execution as asynchronous background work: submit turns from cells, let hooks/webhooks inject output, then refresh the transcript from persisted events.

## References

| Document | Description |
| --- | --- |
| [Marimo conventions (bubseek)](references/marimo-conventions.md) | Cell isolation, display vs return, variable naming, single-page layout, no mid-cell return, validation, directory `--watch`, embedded data, scanner compatibility — detailed rules and checklist for authoring and generated notebooks |
