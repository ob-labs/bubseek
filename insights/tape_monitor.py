# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo", "pandas", "pyobvector", "sqlalchemy", "pymysql", "python-dotenv"]
# ///
"""Tape Monitor — Bub tapestore (SeekDB/SQLite) dashboard with KPIs and charts.

Tapestore URL: single source bubseek.config.resolve_tapestore_url. When opened via channel,
URL is written to insights/.tapestore-url so kernel reads it; otherwise notebook calls resolve_tapestore_url.
Open via channel: http://localhost:2718/?file=tape_monitor.py
"""

import marimo as mo

app = mo.App(width="full")


def _read_tapestore_url_file() -> str | None:
    """If channel wrote insights/.tapestore-url, return its content. Never raises.
    Channel writes to workspace/insights/.tapestore-url; kernel cwd may be workspace root, so we must
    check both start and start/insights (not only start and parents).
    """
    import contextlib

    with contextlib.suppress(Exception):
        from pathlib import Path

        starts = [Path.cwd().resolve()]
        with contextlib.suppress(Exception):
            import marimo as _mo

            nd = getattr(_mo, "notebook_dir", None)
            if callable(nd):
                nb_dir = nd()
                if nb_dir is not None:
                    starts.insert(0, Path(nb_dir).resolve())
        with contextlib.suppress(NameError):
            if __file__ and str(__file__).strip():
                starts.insert(0, Path(__file__).resolve().parent)
        for start in starts:
            # Check start, then start/insights (channel writes there when cwd=workspace), then parents
            candidates = [start]
            if (start / "insights").is_dir():
                candidates.append(start / "insights")
            for d in [*candidates, *start.parents]:
                f = d / ".tapestore-url"
                if f.is_file():
                    url = f.read_text(encoding="utf-8").strip()
                    if url:
                        return url
    return None


@app.cell
def _():
    import contextlib
    import json
    import os
    from datetime import UTC, datetime
    from pathlib import Path

    import marimo as mo
    import pandas as pd
    from sqlalchemy import create_engine, inspect, text

    _default_sqlite = f"sqlite+pysqlite:///{os.path.expanduser('~/.bub/tapes.db')}"
    tapestore_url = None
    try:
        tapestore_url = _read_tapestore_url_file()
        if not tapestore_url:
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
                tapestore_url = (os.environ.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip() or _default_sqlite
        if not tapestore_url:
            tapestore_url = _default_sqlite
    except Exception:
        tapestore_url = _default_sqlite
    if "oceanbase" in tapestore_url or "mysql" in tapestore_url:
        try:
            import bubseek.oceanbase  # register mysql+oceanbase dialect
        except Exception:
            with contextlib.suppress(ImportError):
                import bubseek.oceanbase  # noqa: F401

    refresh_interval_seconds = 300
    return (
        UTC,
        create_engine,
        datetime,
        inspect,
        json,
        mo,
        pd,
        refresh_interval_seconds,
        tapestore_url,
        text,
    )


@app.cell
def _(mo, refresh_interval_seconds):
    refresh = mo.ui.refresh(
        default_interval=refresh_interval_seconds,
        label="Auto-refresh tape data",
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
    refresh,
    tapestore_url,
    text,
):
    # Depend on refresh so this cell re-runs when user refreshes or auto-refresh fires
    _ = refresh.value

    def get_schema_type(engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if "bub_tape_entries" in tables:
            return "seekdb"
        if "tape_entries" in tables:
            return "sqlite"
        return "unknown"

    def load_tapes(engine, schema_type):
        if schema_type == "seekdb":
            rows = (
                engine
                .connect()
                .execute(
                    text(
                        "SELECT tape_name, COUNT(*) as cnt FROM bub_tape_entries "
                        "WHERE tape_name NOT LIKE '%::archived::%' "
                        "GROUP BY tape_name ORDER BY tape_name"
                    )
                )
                .fetchall()
            )
            return pd.DataFrame([{"tape_name": r[0], "entry_count": r[1]} for r in rows])
        if schema_type == "sqlite":
            rows = (
                engine
                .connect()
                .execute(
                    text(
                        "SELECT t.name, COUNT(e.entry_id) as cnt FROM tapes t "
                        "LEFT JOIN tape_entries e ON t.id = e.tape_id "
                        "GROUP BY t.id ORDER BY t.name"
                    )
                )
                .fetchall()
            )
            return pd.DataFrame([{"tape_name": r[0], "entry_count": r[1]} for r in rows])
        return pd.DataFrame()

    def load_kind_stats(engine, schema_type):
        if schema_type == "seekdb":
            rows = (
                engine
                .connect()
                .execute(
                    text(
                        "SELECT kind, COUNT(*) as count FROM bub_tape_entries "
                        "WHERE tape_name NOT LIKE '%::archived::%' GROUP BY kind ORDER BY count DESC"
                    )
                )
                .fetchall()
            )
        elif schema_type == "sqlite":
            rows = (
                engine
                .connect()
                .execute(
                    text("SELECT e.kind, COUNT(*) as count FROM tape_entries e GROUP BY e.kind ORDER BY count DESC")
                )
                .fetchall()
            )
        else:
            rows = []
        return pd.DataFrame([{"kind": r[0], "count": r[1]} for r in rows])

    def load_recent_entries(engine, schema_type, limit=100):
        def extract_preview(payload):
            if not isinstance(payload, dict):
                return ""
            c = payload.get("content", "") or payload.get("message", "") or payload.get("text", "")
            return str(c)[:100] + "..." if len(str(c)) > 100 else str(c)

        if schema_type == "seekdb":
            r = (
                engine
                .connect()
                .execute(
                    text(
                        """
                    SELECT tape_name, entry_id, kind, created_at, payload_json
                    FROM bub_tape_entries
                    WHERE tape_name NOT LIKE '%::archived::%'
                    ORDER BY created_at DESC LIMIT :limit
                    """
                    ),
                    {"limit": limit},
                )
                .fetchall()
            )
        elif schema_type == "sqlite":
            r = (
                engine
                .connect()
                .execute(
                    text(
                        """
                    SELECT t.name, e.entry_id, e.kind, e.created_at, e.payload
                    FROM tape_entries e JOIN tapes t ON e.tape_id = t.id
                    ORDER BY e.created_at DESC LIMIT :limit
                    """
                    ),
                    {"limit": limit},
                )
                .fetchall()
            )
        else:
            r = []
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
        """Load recent created_at for time-series aggregation in pandas."""
        if schema_type == "seekdb":
            rows = (
                engine
                .connect()
                .execute(
                    text(
                        """
                    SELECT created_at FROM bub_tape_entries
                    WHERE tape_name NOT LIKE '%::archived::%'
                    ORDER BY created_at DESC LIMIT :limit
                    """
                    ),
                    {"limit": limit},
                )
                .fetchall()
            )
        elif schema_type == "sqlite":
            rows = (
                engine
                .connect()
                .execute(
                    text("SELECT e.created_at FROM tape_entries e ORDER BY e.created_at DESC LIMIT :limit"),
                    {"limit": limit},
                )
                .fetchall()
            )
        else:
            return pd.DataFrame(columns=["date", "count"])
        if not rows:
            return pd.DataFrame(columns=["date", "count"])
        df = pd.DataFrame([r[0] for r in rows], columns=["created_at"])
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df = df.dropna(subset=["created_at"])
        df["date"] = df["created_at"].dt.date
        daily = df["date"].value_counts().sort_index().reset_index()
        daily.columns = ["date", "count"]
        return daily

    try:
        engine = create_engine(tapestore_url, pool_pre_ping=True)
        schema_type = get_schema_type(engine)
        tapes_df = load_tapes(engine, schema_type)
        kind_stats = load_kind_stats(engine, schema_type)
        recent_df = load_recent_entries(engine, schema_type, 100)
        daily_df = load_created_at_series(engine, schema_type, 5000)
        engine.dispose()
    except Exception as e:
        tapes_df = pd.DataFrame([{"tape_name": f"Error: {e}", "entry_count": 0}])
        kind_stats = pd.DataFrame([{"kind": "error", "count": 0}])
        recent_df = pd.DataFrame([
            {
                "tape": "Error",
                "entry_id": 0,
                "kind": "error",
                "created_at": str(datetime.now(UTC))[:19],
                "content_preview": str(e),
            }
        ])
        daily_df = pd.DataFrame(columns=["date", "count"])
        schema_type = "unknown"

    return (
        daily_df,
        get_schema_type,
        kind_stats,
        load_created_at_series,
        load_kind_stats,
        load_recent_entries,
        load_tapes,
        recent_df,
        schema_type,
        tapes_df,
    )


@app.cell
def _(kind_stats, mo, schema_type, tapes_df):
    total_tapes = len(tapes_df)
    total_entries = int(tapes_df["entry_count"].sum()) if not tapes_df.empty else 0
    kpi = mo.md(f"**Tapes:** {total_tapes} · **Entries:** {total_entries} · **Store:** {schema_type}")
    return (kpi, total_entries, total_tapes)


@app.cell
def _(kind_stats, mo):
    if kind_stats.empty:
        kind_chart = mo.md("*No kind stats.*")
    else:
        _max_c = kind_stats["count"].max() or 1
        _bars = []
        _y = 28
        for _, _row in kind_stats.head(12).iterrows():
            _w = int((_row["count"] / _max_c) * 220)
            _label = str(_row["kind"])[:20]
            _bars.append(
                f'<text x="8" y="{_y}" font-size="12" fill="#334155">{_label}</text>'
                f'<rect x="120" y="{_y - 12}" rx="4" width="{_w}" height="18" fill="#2563eb"/>'
                f'<text x="{128 + _w}" y="{_y}" font-size="11" fill="#64748b">{_row["count"]}</text>'
            )
            _y += 28
        _h = _y + 10
        _svg = f'<svg width="360" height="{_h}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8fafc"/>{chr(10).join(_bars)}</svg>'
        kind_chart = mo.vstack(
            [
                mo.md("#### Entries by kind"),
                mo.Html(_svg),
            ],
            gap=0.5,
        )
    return (kind_chart,)


@app.cell
def _(mo, tapes_df):
    if tapes_df.empty:
        tape_chart = mo.md("*No tapes.*")
    else:
        _top = tapes_df.nlargest(12, "entry_count")
        _max_c = _top["entry_count"].max() or 1
        _bars = []
        _y = 28
        for _, _row in _top.iterrows():
            _w = int((_row["entry_count"] / _max_c) * 220)
            _label = (_row["tape_name"] or "")[:22]
            _bars.append(
                f'<text x="8" y="{_y}" font-size="11" fill="#334155">{_label}</text>'
                f'<rect x="140" y="{_y - 12}" rx="4" width="{_w}" height="18" fill="#059669"/>'
                f'<text x="{150 + _w}" y="{_y}" font-size="11" fill="#64748b">{int(_row["entry_count"])}</text>'
            )
            _y += 28
        _h = _y + 10
        _svg = f'<svg width="380" height="{_h}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8fafc"/>{chr(10).join(_bars)}</svg>'
        tape_chart = mo.vstack(
            [
                mo.md("#### Entries per tape (top 12)"),
                mo.Html(_svg),
            ],
            gap=0.5,
        )
    return (tape_chart,)


@app.cell
def _(daily_df, mo, pd):
    if daily_df.empty or len(daily_df) < 2:
        time_chart = mo.md("*No daily data.*")
    else:
        _df = daily_df.tail(21)
        _max_c = _df["count"].max() or 1
        _bars = []
        _x0, _y0, _w_bar = 40, 24, 12
        for _i, (_, _row) in enumerate(_df.iterrows()):
            _h = int((_row["count"] / _max_c) * 120)
            _x = _x0 + _i * (_w_bar + 4)
            _bars.append(f'<rect x="{_x}" y="{_y0 + 120 - _h}" width="{_w_bar}" height="{_h}" fill="#7c3aed" rx="2"/>')
        _labels = []
        for _i, (_, _row) in enumerate(_df.iterrows()):
            if _i % 5 == 0:
                _d = str(_row["date"])[-5:]
                _x = _x0 + _i * (_w_bar + 4)
                _labels.append(f'<text x="{_x}" y="{_y0 + 138}" font-size="9" fill="#64748b">{_d}</text>')
        _width = _x0 + len(_df) * (_w_bar + 4) + 20
        _height = 165
        _svg = f'<svg width="{_width}" height="{_height}" xmlns="http://www.w3.org/2000/svg"><rect width="100%" height="100%" fill="#f8fafc"/>{chr(10).join(_bars)}{chr(10).join(_labels)}</svg>'
        time_chart = mo.vstack(
            [
                mo.md("#### Entries over time (last 21 days)"),
                mo.Html(_svg),
            ],
            gap=0.5,
        )
    return (time_chart,)


@app.cell
def _(mo, recent_df):
    if recent_df.empty:
        entries_block = mo.md("### No recent entries.")
    else:
        entries_block = mo.vstack(
            [
                mo.md("### Recent entries (last 100)"),
                mo.ui.table(recent_df, page_size=20, pagination=True),
            ],
            gap=0.5,
        )
    return (entries_block,)


@app.cell
def _(
    entries_block,
    kind_chart,
    kpi,
    mo,
    refresh,
    tape_chart,
    time_chart,
):
    page = mo.vstack(
        [
            mo.md("# 📼 Bub Tape Monitor"),
            mo.md("*SeekDB / SQLite tapestore. Auto-refresh every 5 min or click to refresh.*"),
            refresh,
            kpi,
            mo.hstack([kind_chart, tape_chart, time_chart], widths=[1, 1, 1], gap=1.0),
            entries_block,
        ],
        gap=1.0,
    )
    page  # noqa: B018  # last expression for marimo display
    return (page,)


if __name__ == "__main__":
    app.run()
