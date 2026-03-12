# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo"]
# ///

"""A compact Iris notebook used as a sample insight for Bubseek."""

import marimo as mo

app = mo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    iris_rows = [
        {"species": "Setosa", "sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2},
        {"species": "Setosa", "sepal_length": 4.9, "sepal_width": 3.0, "petal_length": 1.4, "petal_width": 0.2},
        {"species": "Versicolor", "sepal_length": 7.0, "sepal_width": 3.2, "petal_length": 4.7, "petal_width": 1.4},
        {"species": "Versicolor", "sepal_length": 6.4, "sepal_width": 3.2, "petal_length": 4.5, "petal_width": 1.5},
        {"species": "Virginica", "sepal_length": 6.3, "sepal_width": 3.3, "petal_length": 6.0, "petal_width": 2.5},
        {"species": "Virginica", "sepal_length": 5.8, "sepal_width": 2.7, "petal_length": 5.1, "petal_width": 1.9},
    ]
    return (iris_rows, mo)


@app.cell
def _(mo):
    title = mo.md("# Iris Snapshot")
    title
    return (title,)


@app.cell
def _(iris_rows):
    species_counts: dict[str, int] = {}
    feature_totals = {
        "sepal_length": 0.0,
        "sepal_width": 0.0,
        "petal_length": 0.0,
        "petal_width": 0.0,
    }

    for row in iris_rows:
        species_counts[row["species"]] = species_counts.get(row["species"], 0) + 1
        for feature in feature_totals:
            feature_totals[feature] += row[feature]

    row_count = len(iris_rows)
    feature_averages = {feature: total / row_count for feature, total in feature_totals.items()}
    return (feature_averages, species_counts)


@app.cell
def _(feature_averages, mo, species_counts):
    summary = mo.md(
        "\n".join([
            "## Summary",
            "",
            f"- Samples: **{sum(species_counts.values())}**",
            f"- Species: **{', '.join(f'{name}={count}' for name, count in species_counts.items())}**",
            f"- Mean sepal length: **{feature_averages['sepal_length']:.2f} cm**",
            f"- Mean petal length: **{feature_averages['petal_length']:.2f} cm**",
        ])
    )
    summary
    return (summary,)


@app.cell
def _(iris_rows, mo):
    table = mo.ui.table(iris_rows, label="Iris rows", selection=None)
    table
    return (table,)


if __name__ == "__main__":
    app.run()
