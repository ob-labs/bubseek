"""Canonical marimo notebook templates for Bubseek insights."""

from __future__ import annotations

from pathlib import Path

NOTEBOOK_NAMES = frozenset({"dashboard.py", "index.py"})

DASHBOARD_NOTEBOOK = '''"""Bubseek Marimo dashboard — native marimo chat plus insights index."""
# marimo.App (for directory scanner)
import marimo as mo

app = mo.App(width="full")


@app.cell
def _():
    import json
    import os
    from pathlib import Path
    from urllib import error as urlerror
    from urllib import request as urlrequest

    import marimo as mo

    api_base = f"http://127.0.0.1:{os.environ.get('BUB_MARIMO_PORT', '2718')}"
    chat_request_timeout_seconds = max(int(os.environ.get("BUB_MARIMO_CHAT_TIMEOUT_SECONDS", "300")) + 30, 120)
    insights_dir = Path(__file__).resolve().parent
    get_history, set_history = mo.state([], allow_self_loops=True)
    get_last_processed_nonce, set_last_processed_nonce = mo.state(0, allow_self_loops=True)
    get_pending_submission, set_pending_submission = mo.state(
        {"nonce": 0, "content": ""},
        allow_self_loops=True,
    )
    get_session_id, set_session_id = mo.state(None, allow_self_loops=True)
    return (
        api_base,
        chat_request_timeout_seconds,
        get_history,
        get_last_processed_nonce,
        get_pending_submission,
        get_session_id,
        insights_dir,
        json,
        mo,
        set_history,
        set_last_processed_nonce,
        set_pending_submission,
        set_session_id,
        urlerror,
        urlrequest,
    )


@app.cell
def _(mo):
    title = mo.vstack(
        [
            mo.md("# Bubseek Marimo"),
            mo.md("Use native marimo widgets to chat with Bub and browse generated notebooks."),
        ],
        gap=0.5,
    )
    return (title,)


@app.cell
def _(get_history, mo):
    _history = get_history()
    if not _history:
        chat_history = mo.md("*No messages yet.*")
    else:
        _items = []
        for _msg in _history:
            _role = _msg.get("role", "assistant")
            _label = "You" if _role == "user" else "Bub"
            _body = mo.md(_msg.get("content", ""))
            _items.append(mo.vstack([mo.md(f"**{_label}**"), _body], gap=0.25))
        chat_history = mo.vstack(_items, gap=0.75)
    return (chat_history,)


@app.cell
def _(get_pending_submission, mo, set_pending_submission):
    def _submit(value):
        pending = get_pending_submission()
        set_pending_submission(
            {
                "nonce": pending["nonce"] + 1,
                "content": (value or "").strip(),
            }
        )

    chat_form = mo.ui.text_area(
        placeholder="Write a message to Bub. Prefix with ',' for commands.",
        label="Message",
    ).form(
        submit_button_label="Send",
        clear_on_submit=True,
        bordered=True,
        on_change=_submit,
    )
    return (chat_form,)


@app.cell
def _(chat_form, chat_history, mo):
    chat_panel = mo.vstack(
        [
            mo.md("## Chat"),
            chat_history,
            chat_form,
        ],
        gap=0.75,
    )
    return (chat_panel,)


@app.cell
def _(
    api_base,
    chat_request_timeout_seconds,
    get_history,
    get_last_processed_nonce,
    get_pending_submission,
    get_session_id,
    json,
    set_history,
    set_last_processed_nonce,
    set_session_id,
    urlerror,
    urlrequest,
):
    submission = get_pending_submission()
    content = (submission["content"] or "").strip()
    nonce = submission["nonce"]
    if content and nonce != get_last_processed_nonce():
        set_last_processed_nonce(nonce)
        _history = list(get_history())
        _history.append({"role": "user", "content": content})
        set_history(_history)

        payload = {"content": content}
        session_id = get_session_id()
        if session_id:
            payload["session_id"] = session_id

        request = urlrequest.Request(
            f"{api_base}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assistant_messages = []
        try:
            with urlrequest.urlopen(request, timeout=chat_request_timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            _body = exc.read().decode("utf-8", errors="replace")
            assistant_messages.append({"role": "assistant", "content": f"HTTP {exc.code}: {_body}"})
        except Exception as exc:
            assistant_messages.append({"role": "assistant", "content": f"Request failed: {exc}"})
        else:
            if result.get("session_id"):
                set_session_id(result["session_id"])
            for _message in result.get("messages", []):
                text = (_message.get("content") or "").strip()
                if text:
                    assistant_messages.append({"role": "assistant", "content": text})

        if assistant_messages:
            set_history(_history + assistant_messages)


@app.cell
def _(insights_dir, mo):
    refresh_button = mo.ui.run_button(label="Refresh Index")
    notebooks = sorted(
        [path for path in insights_dir.glob("*.py") if path.name not in {"dashboard.py", "index.py"}],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not notebooks:
        notebooks_view = mo.md("*No insight notebooks yet. Ask Bub to generate one.*")
    else:
        lines = ["### Available notebooks"]
        lines.extend(f"- [{path.stem}](/?file={path.name})" for path in notebooks)
        notebooks_view = mo.md("\\n".join(lines))

    index_panel = mo.vstack(
        [
            mo.md("## Insights Index"),
            refresh_button,
            notebooks_view,
        ],
        gap=0.75,
    )
    return (index_panel,)


@app.cell
def _(chat_panel, index_panel, mo, title):
    page = mo.vstack(
        [
            title,
            mo.hstack([chat_panel, index_panel], widths=[0.62, 0.38], align="start", gap=1.0),
        ],
        gap=1.0,
    )
    page
    return (page,)


if __name__ == "__main__":
    app.run()
'''

INDEX_NOTEBOOK = '''"""Bubseek Insights index — open dashboard or browse notebooks."""
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
        page = mo.md("\\n".join(lines))
    else:
        page = mo.md(
            "# Bubseek Insights\\n\\n"
            "- [Open dashboard](/?file=dashboard.py)\\n\\n"
            "- [Open starter visualization example](/?file=example_visualization.py)\\n\\n"
            "No insight notebooks yet. Ask Bub in the dashboard to generate one."
        )
    page
    return (page,)


if __name__ == "__main__":
    app.run()
'''

EXAMPLE_NOTEBOOK = '''# /// script
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
    header
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
            <text x="10" y="{y}" font-size="13" fill="#334155">{row['month']}</text>
            <rect x="72" y="{y - 14}" rx="6" ry="6" width="{width}" height="20" fill="#2563eb"></rect>
            <text x="{82 + width}" y="{y}" font-size="12" fill="#0f172a">{value}</text>
            """
        )
        y += 34

    svg = f"""
    <svg width="420" height="{y}" viewBox="0 0 420 {y}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8fafc"></rect>
      {''.join(bars)}
    </svg>
    """

    summary = mo.md(
        f"### Summary\\n"
        f"- Selected metric: **{selected}**\\n"
        f"- Latest value: **{data[-1][selected]}**\\n"
        f"- Peak value: **{max_value}**"
    )
    chart = mo.Html(svg)
    content = mo.vstack([summary, chart], gap=0.75)
    content
    return (content,)


if __name__ == "__main__":
    app.run()
'''

SEED_NOTEBOOKS = {
    "dashboard.py": DASHBOARD_NOTEBOOK,
    "index.py": INDEX_NOTEBOOK,
    "example_visualization.py": EXAMPLE_NOTEBOOK,
}


def ensure_seed_notebooks(insights_dir: Path) -> list[Path]:
    """Write the canonical dashboard and starter notebooks into the insights directory."""
    insights_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    for name, content in SEED_NOTEBOOKS.items():
        path = insights_dir / name
        path.write_text(content, encoding="utf-8")
        created_paths.append(path)
    return created_paths
