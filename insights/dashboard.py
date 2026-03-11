"""Bubseek Marimo dashboard — native marimo chat + insights index."""
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
    chat_request_timeout_seconds = 330
    insights_dir = Path('/home/shangzhuoran.szr/oceanbase/bubseek/insights')
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
        set_last_processed_nonce,
        set_pending_submission,
        set_history,
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
            _title = "You" if _role == "user" else "Bub"
            _body = mo.md(_msg.get("content", ""))
            _items.append(
                mo.vstack(
                    [
                        mo.md(f"**{_title}**"),
                        _body,
                    ],
                    gap=0.25,
                )
            )
        chat_history = mo.vstack(_items, gap=0.75)
    return (chat_history,)


@app.cell
def _(get_pending_submission, mo, set_pending_submission):
    def _submit(_value):
        _pending = get_pending_submission()
        set_pending_submission(
            {
                "nonce": _pending["nonce"] + 1,
                "content": (_value or "").strip(),
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
    set_last_processed_nonce,
    set_history,
    set_session_id,
    urlerror,
    urlrequest,
):
    _submission = get_pending_submission()
    _content = (_submission["content"] or "").strip()
    _nonce = _submission["nonce"]
    if _content and _nonce != get_last_processed_nonce():
        set_last_processed_nonce(_nonce)

        _history = list(get_history())
        _history.append({"role": "user", "content": _content})
        set_history(_history)

        _payload = {"content": _content}
        _session_id = get_session_id()
        if _session_id:
            _payload["session_id"] = _session_id

        _request = urlrequest.Request(
            f"{api_base}/api/chat",
            data=json.dumps(_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        _assistant_messages = []
        try:
            with urlrequest.urlopen(_request, timeout=chat_request_timeout_seconds) as _response:
                _result = json.loads(_response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:
            _body = exc.read().decode("utf-8", errors="replace")
            _assistant_messages.append({"role": "assistant", "content": f"HTTP {exc.code}: {_body}"})
        except Exception as exc:
            _assistant_messages.append({"role": "assistant", "content": f"Request failed: {exc}"})
        else:
            if _result.get("session_id"):
                set_session_id(_result["session_id"])
            for _message in _result.get("messages", []):
                _text = (_message.get("content") or "").strip()
                if _text:
                    _assistant_messages.append({"role": "assistant", "content": _text})

        if _assistant_messages:
            set_history(_history + _assistant_messages)
    return


@app.cell
def _(insights_dir, mo):
    refresh_btn = mo.ui.run_button(label="Refresh Index")
    notebooks = sorted(
        [p for p in insights_dir.glob("*.py") if p.name not in {"dashboard.py", "index.py"}],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not notebooks:
        notebooks_view = mo.md("*No insight notebooks yet. Ask Bub to generate one.*")
    else:
        _lines = ["### Available notebooks"]
        _lines.extend(f"- [{p.stem}](/?file={p.name})" for p in notebooks)
        notebooks_view = mo.md("\n".join(_lines))

    index_panel = mo.vstack(
        [
            mo.md("## Insights Index"),
            refresh_btn,
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
    return


if __name__ == "__main__":
    app.run()
