# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "pandas", "pyobvector", "sqlalchemy", "pymysql", "python-dotenv"]
# ///
"""Tape Monitor — compact SeekDB tapestore dashboard (tabs: Summary / Runs / Tokens / More).

Tapestore URL: `bubseek.config.resolve_tapestore_url` · Marimo: `http://localhost:2718/?file=tape_monitor.py`
"""

import marimo as mo

app = mo.App(width="full")


@app.cell
def _():
    import contextlib
    import json
    import os
    import re
    from datetime import UTC, datetime
    from pathlib import Path
    from urllib.parse import urlparse

    import marimo as mo
    import pandas as pd
    from sqlalchemy import create_engine, inspect, text

    _default_seekdb = "mysql+oceanbase://root:@127.0.0.1:2881/bub"
    tapestore_url = None
    try:
        try:
            from bubseek.config import resolve_tapestore_url

            discover = None
            with contextlib.suppress(Exception):
                nd = getattr(mo, "notebook_dir", None)
                if callable(nd) and nd() is not None:
                    discover = Path(nd()).resolve()
            if discover is None:
                with contextlib.suppress(NameError):
                    if __file__ and str(__file__).strip():
                        discover = Path(__file__).resolve().parent
            tapestore_url = resolve_tapestore_url(workspace=None, discover_from=discover)
        except Exception:
            tapestore_url = (os.environ.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip() or _default_seekdb
        if not tapestore_url:
            tapestore_url = _default_seekdb
    except Exception:
        tapestore_url = _default_seekdb
    if "oceanbase" in tapestore_url or "mysql" in tapestore_url:
        with contextlib.suppress(ImportError):
            import bubseek.oceanbase  # noqa: F401

    refresh_interval_seconds = 300
    # Light shell aligned with Marimo default chrome (tables stay readable).
    theme_css = """
<style>
:root {
  --tm-bg: #f1f5f9;
  --tm-surface: #ffffff;
  --tm-border: #e2e8f0;
  --tm-text: #0f172a;
  --tm-muted: #64748b;
  --tm-ok: #059669;
  --tm-warn: #d97706;
  --tm-err: #dc2626;
  --tm-accent: #0369a1;
  --tm-accent2: #6d28d9;
  --tm-chart-bg: #e8edf3;
  --tm-badge-bg: #e0f2fe;
}
.tm-wrap {
  font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
  color: var(--tm-text);
  background: var(--tm-bg);
  padding: 1.1rem 1.35rem;
  border-radius: 14px;
  border: 1px solid var(--tm-border);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.tm-h1 { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.03em; margin: 0 0 0.25rem 0; color: var(--tm-text); }
.tm-sub { color: var(--tm-muted); font-size: 0.875rem; line-height: 1.45; margin-bottom: 1rem; max-width: 58rem; }
.tm-sub code { font-size: 0.8em; background: var(--tm-surface); padding: 0.1em 0.35em; border-radius: 4px; border: 1px solid var(--tm-border); }
.tm-grid-kpi { display: grid; grid-template-columns: repeat(auto-fill, minmax(148px, 1fr)); gap: 0.6rem; margin: 0.65rem 0 0.25rem 0; }
.tm-kpi {
  background: var(--tm-surface);
  border: 1px solid var(--tm-border);
  border-radius: 10px;
  padding: 0.65rem 0.8rem;
  min-height: 4.25rem;
  box-shadow: 0 1px 0 rgba(255,255,255,0.9) inset;
}
.tm-kpi label { display: block; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.07em; color: var(--tm-muted); font-weight: 600; }
.tm-kpi .tm-val { display: block; font-size: 1.28rem; font-weight: 700; color: var(--tm-accent); margin-top: 0.15rem; font-variant-numeric: tabular-nums; }
.tm-section { margin-top: 1.15rem; padding-top: 0.85rem; border-top: 1px solid var(--tm-border); }
.tm-section h2 { font-size: 1rem; margin: 0 0 0.45rem 0; color: var(--tm-accent2); font-weight: 650; }
.tm-badge { display: inline-block; font-size: 0.62rem; padding: 0.14rem 0.5rem; border-radius: 999px; background: var(--tm-badge-bg); color: var(--tm-accent); margin-right: 0.35rem; font-weight: 600; border: 1px solid #bae6fd; }
.tm-callout { background: var(--tm-surface); border: 1px solid var(--tm-border); border-left: 4px solid var(--tm-warn); padding: 0.75rem 1rem; border-radius: 0 10px 10px 0; font-size: 0.82rem; color: var(--tm-muted); margin: 0.75rem 0 0 0; line-height: 1.5; }
.tm-callout code { font-size: 0.85em; background: var(--tm-bg); padding: 0.08em 0.3em; border-radius: 4px; }
.tm-divider { height: 1px; background: linear-gradient(90deg, transparent, var(--tm-border), transparent); margin: 1rem 0; border: 0; }
</style>
"""
    return (
        UTC,
        theme_css,
        create_engine,
        datetime,
        inspect,
        json,
        mo,
        os,
        pd,
        re,
        refresh_interval_seconds,
        tapestore_url,
        text,
        urlparse,
    )


@app.cell
def _(mo, refresh_interval_seconds):
    refresh = mo.ui.refresh(
        default_interval=refresh_interval_seconds,
        label="Refresh tape data",
    )
    return (refresh,)


@app.cell
def _(  # noqa: C901
    UTC,
    create_engine,
    datetime,
    inspect,
    json,
    pd,
    re,
    refresh,
    tapestore_url,
    text,
):
    _ = refresh.value

    archived_like = "%::archived::%"

    def get_schema_type(engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if "tapes" in tables and "tape_entries" in tables:
            return "seekdb"
        return "unknown"

    def load_tapes(engine, schema_type):
        if schema_type != "seekdb":
            return pd.DataFrame()
        rows = (
            engine
            .connect()
            .execute(
                text(
                    """
                    SELECT t.name, COUNT(e.entry_id) as cnt
                    FROM tapes t
                    LEFT JOIN tape_entries e ON t.id = e.tape_id
                    WHERE t.name NOT LIKE :archived_like
                    GROUP BY t.id, t.name
                    ORDER BY t.name
                    """
                ),
                {"archived_like": archived_like},
            )
            .fetchall()
        )
        return pd.DataFrame([{"tape_name": r[0], "entry_count": r[1]} for r in rows])

    def load_kind_stats(engine, schema_type):
        if schema_type != "seekdb":
            return pd.DataFrame()
        rows = (
            engine
            .connect()
            .execute(
                text(
                    """
                    SELECT e.kind, COUNT(*) as count
                    FROM tape_entries e
                    JOIN tapes t ON e.tape_id = t.id
                    WHERE t.name NOT LIKE :archived_like
                    GROUP BY e.kind
                    ORDER BY count DESC
                    """
                ),
                {"archived_like": archived_like},
            )
            .fetchall()
        )
        return pd.DataFrame([{"kind": r[0], "count": r[1]} for r in rows])

    def load_recent_entries(engine, schema_type, limit=100):
        def extract_preview(payload):
            if not isinstance(payload, dict):
                return ""
            c = payload.get("content", "") or payload.get("message", "") or payload.get("text", "")
            return str(c)[:100] + "..." if len(str(c)) > 100 else str(c)

        if schema_type != "seekdb":
            return pd.DataFrame()
        r = (
            engine
            .connect()
            .execute(
                text(
                    """
                    SELECT t.name, e.entry_id, e.kind, e.created_at, e.payload
                    FROM tape_entries e
                    JOIN tapes t ON e.tape_id = t.id
                    WHERE t.name NOT LIKE :archived_like
                    ORDER BY e.created_at DESC LIMIT :limit
                    """
                ),
                {"archived_like": archived_like, "limit": limit},
            )
            .fetchall()
        )
        out = []
        for row in r:
            tape_name, entry_id, kind, created_at, payload_raw = row
            try:
                payload = json.loads(payload_raw) if payload_raw else {}
            except Exception:
                payload = {}
            out.append({
                "tape": tape_name,
                "entry_id": entry_id,
                "kind": kind,
                "created_at": str(created_at)[:19] if created_at else "",
                "content_preview": extract_preview(payload),
            })
        return pd.DataFrame(out)

    def load_created_at_series(engine, schema_type, limit=5000):
        if schema_type != "seekdb":
            return pd.DataFrame(columns=["date", "count"])
        rows = (
            engine
            .connect()
            .execute(
                text(
                    """
                    SELECT e.created_at
                    FROM tape_entries e
                    JOIN tapes t ON e.tape_id = t.id
                    WHERE t.name NOT LIKE :archived_like
                    ORDER BY e.created_at DESC LIMIT :limit
                    """
                ),
                {"archived_like": archived_like, "limit": limit},
            )
            .fetchall()
        )
        if not rows:
            return pd.DataFrame(columns=["date", "count"])
        df = pd.DataFrame([r[0] for r in rows], columns=["created_at"])
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.dropna(subset=["created_at"])
        df["date"] = df["created_at"].dt.date
        daily = df["date"].value_counts().sort_index().reset_index()
        daily.columns = ["date", "count"]
        return daily

    def load_run_summaries(engine, schema_type, limit_runs=80):
        """Aggregate by run_id: user/assistant counts, tools, wall time."""
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT
              t.name AS tape_name,
              JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.run_id')) AS run_id,
              MIN(e.created_at) AS started_at,
              MAX(e.created_at) AS ended_at,
              SUM(CASE WHEN e.kind = 'message'
                  AND JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.role')) = 'user' THEN 1 ELSE 0 END) AS user_msgs,
              SUM(CASE WHEN e.kind = 'message'
                  AND JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.role')) = 'assistant' THEN 1 ELSE 0 END) AS asst_msgs,
              SUM(CASE WHEN e.kind = 'tool_call' THEN 1 ELSE 0 END) AS tool_calls,
              SUM(CASE WHEN e.kind = 'tool_result' THEN 1 ELSE 0 END) AS tool_results,
              SUM(CASE WHEN e.kind = 'event' THEN 1 ELSE 0 END) AS events,
              COUNT(*) AS entries
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like
              AND JSON_EXTRACT(e.meta, '$.run_id') IS NOT NULL
            GROUP BY t.name, run_id
            HAVING run_id IS NOT NULL AND run_id != ''
            ORDER BY MAX(e.created_at) DESC
            LIMIT :lim
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like, "lim": limit_runs}).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([
            dict(
                zip(
                    [
                        "tape_name",
                        "run_id",
                        "started_at",
                        "ended_at",
                        "user_msgs",
                        "asst_msgs",
                        "tool_calls",
                        "tool_results",
                        "events",
                        "entries",
                    ],
                    r,
                    strict=False,
                )
            )
            for r in rows
        ])
        df["started_at"] = pd.to_datetime(df["started_at"], errors="coerce")
        df["ended_at"] = pd.to_datetime(df["ended_at"], errors="coerce")
        df["wall_s"] = (df["ended_at"] - df["started_at"]).dt.total_seconds().fillna(0)
        # Proxy for “rounds”: user messages (includes “Continue the task” continuations)
        df["rounds_proxy"] = df["user_msgs"].astype(int)
        df["tool_mismatch"] = (df["tool_calls"] != df["tool_results"]).astype(int)
        return df

    def load_event_spans(engine, schema_type, limit=400):
        """Event rows as spans: meta.payload.elapsed_ms / status / name."""
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT
              t.name AS tape_name,
              e.created_at,
              JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.run_id')) AS run_id,
              JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.name')) AS span_name,
              JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.status')) AS status,
              CAST(JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.elapsed_ms')) AS SIGNED) AS elapsed_ms,
              LEFT(JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.output')), 240) AS output_preview
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like
              AND e.kind = 'event'
              AND JSON_EXTRACT(e.meta, '$.payload.name') IS NOT NULL
            ORDER BY e.created_at DESC
            LIMIT :lim
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like, "lim": limit}).fetchall()
        cols = ["tape_name", "created_at", "run_id", "span_name", "status", "elapsed_ms", "output_preview"]
        return pd.DataFrame([dict(zip(cols, r, strict=False)) for r in rows])

    def load_anchors(engine, schema_type, limit=60):
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT t.name AS tape_name, e.entry_id, e.anchor_name, e.created_at, e.payload
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like AND e.kind = 'anchor'
            ORDER BY e.created_at DESC
            LIMIT :lim
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like, "lim": limit}).fetchall()
        out = []
        for tape_name, entry_id, anchor_name, created_at, payload_raw in rows:
            try:
                p = json.loads(payload_raw) if payload_raw else {}
            except Exception:
                p = {}
            state = p.get("state") if isinstance(p.get("state"), dict) else {}
            state_keys = ", ".join(sorted(state.keys())) if state else ""
            out.append({
                "tape": tape_name,
                "entry_id": entry_id,
                "anchor": anchor_name or p.get("name", ""),
                "created_at": str(created_at)[:19] if created_at else "",
                "state_keys": state_keys,
                "state_preview": str(state)[:120],
            })
        return pd.DataFrame(out)

    def load_handoff_signals(engine, schema_type, limit=40):
        """User messages suggesting handoff / continuation."""
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT t.name AS tape_name,
                   JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.run_id')) AS run_id,
                   e.created_at,
                   LEFT(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content')), 200) AS snippet
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like
              AND e.kind = 'message'
              AND JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.role')) = 'user'
              AND (
                JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content')) LIKE '%Continue the task%'
                OR JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content')) LIKE '%handoff%'
                OR JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content')) LIKE '%context window%'
                OR JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content')) LIKE '%上下文%'
              )
            ORDER BY e.created_at DESC
            LIMIT :lim
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like, "lim": limit}).fetchall()
        return pd.DataFrame([
            dict(zip(["tape_name", "run_id", "created_at", "snippet"], r, strict=False)) for r in rows
        ])

    def load_context_breakdown(engine, schema_type):
        """Per-tape char totals by role; est_tokens ≈ chars/4."""
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT
              t.name AS tape_name,
              SUM(CASE WHEN e.kind = 'system' THEN CHAR_LENGTH(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content'))) ELSE 0 END) AS sys_chars,
              SUM(CASE WHEN e.kind = 'message' AND JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.role')) = 'user'
                  THEN CHAR_LENGTH(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content'))) ELSE 0 END) AS user_chars,
              SUM(CASE WHEN e.kind = 'message' AND JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.role')) = 'assistant'
                  THEN CHAR_LENGTH(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.content'))) ELSE 0 END) AS asst_chars,
              SUM(CASE WHEN e.kind = 'tool_call' THEN 1 ELSE 0 END) AS tool_calls,
              SUM(CASE WHEN e.kind = 'tool_result' THEN 1 ELSE 0 END) AS tool_results
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like
            GROUP BY t.name
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like}).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame([
            dict(
                zip(
                    ["tape_name", "sys_chars", "user_chars", "asst_chars", "tool_calls", "tool_results"],
                    r,
                    strict=False,
                )
            )
            for r in rows
        ])
        for c in ["sys_chars", "user_chars", "asst_chars"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        df["total_chars"] = df["sys_chars"] + df["user_chars"] + df["asst_chars"]
        df["est_tokens"] = (df["total_chars"] / 4).round(0).astype(int)
        return df.sort_values("est_tokens", ascending=False)

    def load_tape_info_snippets(engine, schema_type, limit=25):
        """Parse tape.info text for last_token_usage / entries_since_last_anchor."""
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT t.name, e.created_at, JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.output')) AS output
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like
              AND e.kind = 'event'
              AND JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.name')) = 'tape.info'
            ORDER BY e.created_at DESC
            LIMIT :lim
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like, "lim": limit}).fetchall()

        def parse_info(txt: str) -> dict[str, str]:
            if not txt:
                return {}
            out = {}
            for pat, key in [
                (r"last_token_usage:\s*(\S+)", "last_token_usage"),
                (r"entries_since_last_anchor:\s*(\d+)", "entries_since_anchor"),
                (r"last_anchor:\s*(\S+)", "last_anchor"),
                (r"anchors:\s*(\d+)", "anchors"),
                (r"entries:\s*(\d+)", "entries"),
            ]:
                m = re.search(pat, txt, re.I)
                if m:
                    out[key] = m.group(1).strip()
            return out

        out_rows = []
        for name, created_at, output in rows:
            p = parse_info(output or "")
            out_rows.append({
                "tape": name,
                "created_at": str(created_at)[:19] if created_at else "",
                "last_token_usage": p.get("last_token_usage", "-"),
                "entries_since_anchor": p.get("entries_since_anchor", "-"),
                "last_anchor": p.get("last_anchor", "-"),
                "snippet": (output or "")[:180].replace("\n", " "),
            })
        return pd.DataFrame(out_rows)

    def load_llm_usage_rounds(engine, schema_type, limit_rows=500):
        """Event rows carrying `payload.data.usage` (per model call / round)."""
        if schema_type != "seekdb":
            return pd.DataFrame()
        sql = text(
            """
            SELECT t.name AS tape_name,
                   e.tape_id,
                   e.entry_id,
                   e.created_at,
                   JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.run_id')) AS run_id,
                   JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.name')) AS event_name,
                   JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.data.model')) AS model,
                   CAST(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.data.usage.prompt_tokens')) AS SIGNED) AS prompt_tokens,
                   CAST(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.data.usage.completion_tokens')) AS SIGNED) AS completion_tokens,
                   CAST(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.data.usage.total_tokens')) AS SIGNED) AS total_tokens,
                   CAST(JSON_UNQUOTE(JSON_EXTRACT(e.payload, '$.data.usage.prompt_tokens_details.cached_tokens')) AS SIGNED) AS cached_tokens,
                   CAST(JSON_UNQUOTE(JSON_EXTRACT(e.meta, '$.payload.step')) AS SIGNED) AS step_meta
            FROM tape_entries e
            JOIN tapes t ON e.tape_id = t.id
            WHERE t.name NOT LIKE :archived_like
              AND e.kind = 'event'
              AND JSON_EXTRACT(e.payload, '$.data.usage') IS NOT NULL
            ORDER BY e.created_at DESC
            LIMIT :lim
            """
        )
        rows = engine.connect().execute(sql, {"archived_like": archived_like, "lim": limit_rows}).fetchall()
        cols = [
            "tape_name",
            "tape_id",
            "entry_id",
            "created_at",
            "run_id",
            "event_name",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cached_tokens",
            "step_meta",
        ]
        df = pd.DataFrame([dict(zip(cols, r, strict=False)) for r in rows])
        if df.empty:
            return df
        for c in ["prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "step_meta"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.sort_values(["tape_name", "run_id", "entry_id"], kind="mergesort")
        df["round_seq"] = df.groupby(["tape_name", "run_id"], sort=False).cumcount() + 1
        df["round_label"] = [
            int(sm) if pd.notna(sm) and float(sm) > 0 else int(rs)
            for sm, rs in zip(df["step_meta"], df["round_seq"], strict=False)
        ]
        return df.sort_values("created_at", ascending=False)

    try:
        engine = create_engine(tapestore_url, pool_pre_ping=True)
        schema_type = get_schema_type(engine)
        tapes_df = load_tapes(engine, schema_type)
        kind_stats = load_kind_stats(engine, schema_type)
        recent_df = load_recent_entries(engine, schema_type, 100)
        daily_df = load_created_at_series(engine, schema_type, 5000)
        runs_df = load_run_summaries(engine, schema_type, 80)
        spans_df = load_event_spans(engine, schema_type, 400)
        anchors_df = load_anchors(engine, schema_type, 60)
        handoff_df = load_handoff_signals(engine, schema_type, 40)
        context_df = load_context_breakdown(engine, schema_type)
        tape_info_df = load_tape_info_snippets(engine, schema_type, 25)
        llm_usage_df = load_llm_usage_rounds(engine, schema_type, 500)
        engine.dispose()
    except Exception as e:
        tapes_df = pd.DataFrame([{"tape_name": f"Error: {e}", "entry_count": 0}])
        kind_stats = pd.DataFrame([{"kind": "error", "count": 0}])
        recent_df = pd.DataFrame()
        daily_df = pd.DataFrame(columns=["date", "count"])
        runs_df = pd.DataFrame()
        spans_df = pd.DataFrame()
        anchors_df = pd.DataFrame()
        handoff_df = pd.DataFrame()
        context_df = pd.DataFrame()
        tape_info_df = pd.DataFrame()
        llm_usage_df = pd.DataFrame()
        schema_type = "unknown"

    return (
        anchors_df,
        context_df,
        daily_df,
        get_schema_type,
        handoff_df,
        kind_stats,
        llm_usage_df,
        load_created_at_series,
        load_kind_stats,
        load_recent_entries,
        load_tapes,
        recent_df,
        runs_df,
        schema_type,
        spans_df,
        tape_info_df,
        tapes_df,
    )


@app.cell
def _(llm_usage_df, mo):
    """Tape picker for LLM chart — separate cell so we may read `.value` in the dashboard cell."""
    if llm_usage_df is not None and not llm_usage_df.empty:
        tape_names = sorted(
            llm_usage_df["tape_name"].dropna().astype(str).unique().tolist(),
            key=lambda s: s.lower(),
        )
        llm_tape_picker = mo.ui.dropdown(
            options=tape_names,
            value=tape_names[0],
            label="Tape",
        )
    else:
        llm_tape_picker = mo.ui.dropdown(
            options=["(no LLM usage rows)"],
            value="(no LLM usage rows)",
            label="Tape",
        )
    return (llm_tape_picker,)


@app.cell
def _(  # noqa: C901
    theme_css,
    anchors_df,
    context_df,
    daily_df,
    handoff_df,
    kind_stats,
    llm_usage_df,
    llm_tape_picker,
    mo,
    pd,
    recent_df,
    refresh,
    runs_df,
    schema_type,
    spans_df,
    tape_info_df,
    tapes_df,
    tapestore_url,
    urlparse,
):
    def _store_endpoint(url: str) -> str:
        if not url:
            return "—"
        try:
            p = urlparse(url)
            host = p.hostname or ""
            port = f":{p.port}" if p.port else ""
            db = (p.path or "").strip("/").split("/")[-1] if p.path else ""
            tail = f"/{db}" if db else ""
        except Exception:
            return "—"
        else:
            return f"{host}{port}{tail}" if host else "—"

    store_ep = _store_endpoint(tapestore_url or "")
    chart_bg = "#e8edf3"
    chart_muted = "#64748b"
    chart_label = "#475569"
    chart_text = "#0f172a"
    fill_prompt = "#059669"
    fill_completion = "#7c3aed"
    fill_bar_green = "#059669"

    total_tapes = len(tapes_df)
    total_entries = int(tapes_df["entry_count"].sum()) if not tapes_df.empty else 0
    n_runs = len(runs_df) if runs_df is not None and not runs_df.empty else 0
    n_anchors = len(anchors_df) if anchors_df is not None and not anchors_df.empty else 0
    handoff_hits = len(handoff_df) if handoff_df is not None and not handoff_df.empty else 0
    span_rows = len(spans_df) if spans_df is not None and not spans_df.empty else 0
    n_llm_usage = len(llm_usage_df) if llm_usage_df is not None and not llm_usage_df.empty else 0

    store_one_liner = f"{schema_type} · {store_ep}"
    kpi_html = f"""
{theme_css}
<div class="tm-wrap">
  <div class="tm-h1">Tape monitor</div>
  <div class="tm-sub">SeekDB tapestore — use tabs below. Refresh reloads all queries.</div>
  <div class="tm-grid-kpi">
    <div class="tm-kpi"><label>Tapes</label><span class="tm-val">{total_tapes}</span></div>
    <div class="tm-kpi"><label>Entries</label><span class="tm-val">{total_entries}</span></div>
    <div class="tm-kpi"><label>Runs</label><span class="tm-val">{n_runs}</span></div>
    <div class="tm-kpi"><label>Usage rows</label><span class="tm-val">{n_llm_usage}</span></div>
    <div class="tm-kpi" style="grid-column: span 2; min-width: 14rem;"><label>Store</label><span class="tm-val" style="font-size:0.9rem;font-weight:650;">{store_one_liner}</span></div>
  </div>
</div>
"""

    tape_info_block = mo.md("*No `tape.info` rows.*")
    if tape_info_df is not None and not tape_info_df.empty:
        tape_info_block = mo.vstack(
            [
                mo.md("**tape.info** (token / anchor hints when present)."),
                mo.ui.table(tape_info_df, page_size=6, pagination=True),
            ],
            gap=0.35,
        )

    tool_per_tape = pd.DataFrame()
    if context_df is not None and not context_df.empty and "tool_calls" in context_df.columns:
        _tc = pd.to_numeric(context_df["tool_calls"], errors="coerce").fillna(0).astype(int)
        _tr = pd.to_numeric(context_df["tool_results"], errors="coerce").fillna(0).astype(int)
        tool_per_tape = (
            pd
            .DataFrame({"tape_name": context_df["tape_name"], "tool_calls": _tc, "tool_results": _tr})
            .assign(_s=lambda d: d["tool_calls"] + d["tool_results"])
            .sort_values("_s", ascending=False)
            .drop(columns=["_s"])
            .head(24)
            .reset_index(drop=True)
        )

    tokens_block = mo.md("*No `payload.data.usage` events and no tool_call/tool_result counts in this store.*")
    if llm_usage_df is not None and not llm_usage_df.empty:
        tbl = llm_usage_df[
            [
                "tape_name",
                "run_id",
                "round_label",
                "created_at",
                "model",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            ]
        ].head(40)
        sel_tape = str(llm_tape_picker.value)
        focus = llm_usage_df[llm_usage_df["tape_name"].astype(str) == sel_tape]
        if focus.empty:
            focus = llm_usage_df
        top = focus.sort_values("created_at", ascending=False).iloc[0]
        _rid = top["run_id"]
        if pd.notna(_rid) and str(_rid).strip():
            sub = focus[(focus["run_id"] == _rid)].sort_values("entry_id")
        else:
            sub = focus[focus["entry_id"] == top["entry_id"]].sort_values("entry_id")
        chart_el = mo.md("")
        caption_md = None
        if len(sub) >= 1:
            max_tok = float(
                max(
                    sub["prompt_tokens"].fillna(0).max(),
                    sub["completion_tokens"].fillna(0).max(),
                    1.0,
                )
            )
            svg_w = 720
            bar_x0 = 88
            bar_max = 520
            bar_h = 22
            row_gap = 54
            y0 = 52
            nums_x_right = svg_w - 24
            rows_svg = []
            for i, (_, rw) in enumerate(sub.iterrows()):
                pt = float(rw["prompt_tokens"] or 0)
                ct = float(rw["completion_tokens"] or 0)
                wp = int((pt / max_tok) * bar_max)
                wc = int((ct / max_tok) * bar_max)
                y = y0 + i * row_gap
                lab = f"R{int(rw['round_label'])}"
                bar_bottom = y + 6
                nums_baseline = bar_bottom + 20
                rows_svg.append(
                    f'<text x="12" y="{y + 4}" font-size="16" font-weight="600" fill="{chart_label}">{lab}</text>'
                    f'<rect x="{bar_x0}" y="{y - bar_h + 6}" height="{bar_h}" width="{max(wp, 2)}" fill="{fill_prompt}" rx="4"/>'
                    f'<rect x="{bar_x0 + wp + 6}" y="{y - bar_h + 6}" height="{bar_h}" width="{max(wc, 2)}" fill="{fill_completion}" rx="4"/>'
                    f'<text x="{nums_x_right}" y="{nums_baseline}" text-anchor="end" font-size="14" font-weight="500" fill="{chart_muted}">'
                    f"p {int(pt):,} · c {int(ct):,}</text>"
                )
            leg_x = svg_w - 200
            leg = (
                f'<g transform="translate({leg_x}, 14)">'
                f'<rect x="0" y="0" width="14" height="14" fill="{fill_prompt}" rx="3"/>'
                f'<text x="20" y="12" font-size="13" font-weight="600" fill="{chart_text}">prompt</text>'
                f'<rect x="88" y="0" width="14" height="14" fill="{fill_completion}" rx="3"/>'
                f'<text x="108" y="12" font-size="13" font-weight="600" fill="{chart_text}">completion</text>'
                f"</g>"
            )
            h = y0 + len(sub) * row_gap + 8
            svg = (
                f'<svg width="{svg_w}" height="{h}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {h}">'
                f'<rect width="100%" height="100%" fill="{chart_bg}" rx="8"/>'
                f"{leg}{chr(10).join(rows_svg)}</svg>"
            )
            chart_el = mo.Html(svg)
            rid_disp = str(_rid) if pd.notna(_rid) and str(_rid).strip() else "—"
            rid_one = rid_disp if len(rid_disp) <= 48 else rid_disp[:45] + "…"
            ts = top["created_at"]
            ts_s = str(ts)[:16] if ts is not None and str(ts) else "—"
            caption_md = mo.md(f"Latest run on **{sel_tape}** · `{rid_one}` · {ts_s}")

        tool_line = mo.md("")
        if not tool_per_tape.empty:
            hit = tool_per_tape[tool_per_tape["tape_name"].astype(str) == sel_tape]
            if not hit.empty:
                r0 = hit.iloc[0]
                tool_line = mo.md(
                    f"**Tool entries on this tape** — `tool_call`: **{int(r0['tool_calls'])}** · "
                    f"`tool_result`: **{int(r0['tool_results'])}**"
                )
            else:
                tool_line = mo.md("*No tool_call / tool_result counts for this tape.*")
        else:
            tool_line = mo.md("*No tool_call / tool_result aggregates (refresh after data exists).*")

        tok_parts = [llm_tape_picker]
        if caption_md is not None:
            tok_parts.append(caption_md)
        tok_parts.extend([chart_el, tool_line, mo.ui.table(tbl, page_size=8, pagination=True)])
        tokens_block = mo.vstack(tok_parts, gap=0.55)
    elif not tool_per_tape.empty:
        tokens_block = mo.vstack(
            [
                mo.md("**Tool entries** per tape (`kind=tool_call` / `tool_result` counts). No usage rows in store."),
                mo.ui.table(tool_per_tape, page_size=12, pagination=True),
            ],
            gap=0.4,
        )

    runs_block = mo.md("*No rows with `meta.run_id` to aggregate.*")
    if runs_df is not None and not runs_df.empty:
        rs = runs_df.copy()
        rs["wall_s"] = rs["wall_s"].round(1)
        rs["anomaly"] = rs.apply(
            lambda r: "tool mismatch" if r["tool_mismatch"] else ("long wall time" if r["wall_s"] > 3600 else ""),
            axis=1,
        )
        display_cols = [
            "tape_name",
            "run_id",
            "rounds_proxy",
            "user_msgs",
            "asst_msgs",
            "tool_calls",
            "wall_s",
            "entries",
            "anomaly",
        ]
        runs_block = mo.vstack(
            [
                mo.md("**Runs** — `wall_s` = first→last entry; **anomaly**: tool mismatch or wall &gt; 1h."),
                mo.ui.table(rs[display_cols], page_size=8, pagination=True),
            ],
            gap=0.35,
        )

    span_agg_df = pd.DataFrame()
    if spans_df is not None and not spans_df.empty:
        _sub = spans_df.dropna(subset=["elapsed_ms"]).copy()
        _sub["elapsed_ms"] = pd.to_numeric(_sub["elapsed_ms"], errors="coerce")
        _sub = _sub.dropna(subset=["elapsed_ms"])
        if not _sub.empty:
            span_agg_df = (
                _sub
                .groupby("span_name", as_index=False)["elapsed_ms"]
                .median()
                .sort_values("elapsed_ms", ascending=False)
                .head(20)
                .reset_index(drop=True)
            )

    span_table = (
        mo.ui.table(span_agg_df, page_size=10, pagination=True)
        if not span_agg_df.empty
        else mo.md("*No span timings (`elapsed_ms`).*")
    )

    anchors_block = mo.md("*No anchors.*")
    if anchors_df is not None and not anchors_df.empty:
        anchors_block = mo.vstack(
            [mo.md("**Anchors** (`kind=anchor`)."), mo.ui.table(anchors_df, page_size=6, pagination=True)],
            gap=0.35,
        )

    hand_block = mo.md("*No continuation heuristics.*")
    if handoff_df is not None and not handoff_df.empty:
        hand_block = mo.vstack(
            [
                mo.md("**Continuation hints** (user text heuristic)."),
                mo.ui.table(handoff_df, page_size=5, pagination=True),
            ],
            gap=0.35,
        )

    if daily_df.empty or len(daily_df) < 2:
        activity_el = mo.md("*No daily trend.*")
    else:
        _df = daily_df.tail(14)
        _max_c = _df["count"].max() or 1
        _bars = []
        _x0, _y0, _w_bar = 36, 28, 14
        for _i, (_, _row) in enumerate(_df.iterrows()):
            _h = int((_row["count"] / _max_c) * 100)
            _x = _x0 + _i * (_w_bar + 3)
            _bars.append(
                f'<rect x="{_x}" y="{_y0 + 100 - _h}" width="{_w_bar}" height="{_h}" fill="{fill_bar_green}" rx="2"/>'
            )
        _labels = []
        for _i, (_, _row) in enumerate(_df.iterrows()):
            if _i % 3 == 0 or _i == len(_df) - 1:
                _d = str(_row["date"])[-5:]
                _x = _x0 + _i * (_w_bar + 3)
                _labels.append(f'<text x="{_x}" y="{_y0 + 118}" font-size="9" fill="{chart_muted}">{_d}</text>')
        _width = _x0 + len(_df) * (_w_bar + 3) + 24
        _height = 138
        _svg = f'<svg width="{_width}" height="{_height}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="{chart_bg}" rx="6"/>{chr(10).join(_bars)}{chr(10).join(_labels)}</svg>'
        activity_el = mo.Html(_svg)

    top_tapes_tbl = mo.md("*No tapes.*")
    if not tapes_df.empty and not (tapes_df["tape_name"].astype(str).str.startswith("Error").any()):
        _tt = tapes_df.nlargest(8, "entry_count")[["tape_name", "entry_count"]].reset_index(drop=True)
        top_tapes_tbl = mo.ui.table(_tt, page_size=8, pagination=False)

    kinds_tbl = (
        mo.ui.table(kind_stats.head(16), page_size=12, pagination=True)
        if not kind_stats.empty
        else mo.md("*No kind breakdown.*")
    )

    entries_block = mo.md("*No recent rows.*")
    if recent_df is not None and not recent_df.empty:
        entries_block = mo.vstack(
            [mo.md("**Recent entries** (tail)."), mo.ui.table(recent_df, page_size=12, pagination=True)],
            gap=0.35,
        )

    signals_md = mo.md(
        f"**Signals** — anchors: **{n_anchors}** · handoff hints: **{handoff_hits}** · span rows: **{span_rows}**"
    )

    about_md = mo.md(
        "`run_id` ≈ trace id; `event` payloads may carry `elapsed_ms` / `usage`. "
        "Export to Grafana/OTLP is outside this notebook."
    )

    summary_tab = mo.vstack(
        [
            mo.md("**Activity** — entries per day (14d)."),
            activity_el,
            mo.md("**Top tapes** by entry count."),
            top_tapes_tbl,
        ],
        gap=0.45,
    )

    runs_tab = mo.vstack([runs_block], gap=0.35)

    tokens_tab = tokens_block

    more_tab = mo.accordion(
        {
            "Kinds": kinds_tbl,
            "Span latency (median ms)": span_table,
            "tape.info": tape_info_block,
            "Anchors": anchors_block,
            "Continuations": hand_block,
            "Recent tail": entries_block,
            "Signals & note": mo.vstack([signals_md, about_md], gap=0.4),
        },
        lazy=True,
    )

    main_tabs = mo.ui.tabs(
        {
            "Summary": summary_tab,
            "Runs": runs_tab,
            "Tokens": tokens_tab,
            "More": more_tab,
        },
        value="Summary",
        lazy=True,
    )

    page = mo.vstack(
        [
            refresh,
            mo.Html(kpi_html),
            main_tabs,
        ],
        gap=0.65,
    )
    page  # noqa: B018
    return (page,)


if __name__ == "__main__":
    app.run()
