# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "pyobvector",
#     "sqlalchemy",
#     "pymysql",
#     "python-dotenv",
#     "apscheduler",
# ]
# ///
"""Scheduled tasks — rows from `apscheduler_jobs` (tapestore DB). Marimo: `?file=schedule_kanban.py`.

Marimo expects: PEP 723 block → docstring → `import marimo` → `app = mo.App(...)` with no other
module-level code in between (otherwise the gateway may fail to attach a kernel).
"""

import marimo as mo

app = mo.App(width="full")


@app.cell
def _():  # noqa: C901
    import contextlib
    import os
    import pickle
    from datetime import UTC, datetime
    from pathlib import Path

    import marimo as mo
    from sqlalchemy import MetaData, Table, case, create_engine, inspect, select, text

    _default_seekdb = "mysql+oceanbase://root:@127.0.0.1:2881/bub"

    def _resolve_tapestore_like_gateway() -> str:  # noqa: C901
        """Same DB as bubseek: env → workspace → repo .env (via __file__) → notebook_dir."""
        try:
            from bubseek.config import discover_project_root, resolve_tapestore_url
        except Exception:
            return _default_seekdb

        direct = (os.environ.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip()
        if direct:
            return direct

        ws = (os.environ.get("BUB_WORKSPACE_PATH") or "").strip()
        if ws:
            with contextlib.suppress(Exception):
                return resolve_tapestore_url(workspace=Path(ws).resolve())

        file_parent = None
        with contextlib.suppress(NameError):
            if __file__ and str(__file__).strip():
                file_parent = Path(__file__).resolve().parent
        if file_parent is not None:
            root = discover_project_root(file_parent)
            if root is not None:
                with contextlib.suppress(Exception):
                    return resolve_tapestore_url(workspace=root)

        discover = None
        with contextlib.suppress(Exception):
            nd = getattr(mo, "notebook_dir", None)
            if callable(nd) and nd() is not None:
                discover = Path(nd()).resolve()
        if discover is not None:
            with contextlib.suppress(Exception):
                u = resolve_tapestore_url(workspace=None, discover_from=discover)
                if u:
                    return u

        if file_parent is not None:
            with contextlib.suppress(Exception):
                u = resolve_tapestore_url(workspace=None, discover_from=file_parent)
                if u:
                    return u

        with contextlib.suppress(Exception):
            u = resolve_tapestore_url()
            if u:
                return u
        return _default_seekdb

    try:
        tapestore_url = _resolve_tapestore_like_gateway() or _default_seekdb
    except Exception:
        tapestore_url = _default_seekdb

    if "oceanbase" in tapestore_url or "mysql" in tapestore_url:
        with contextlib.suppress(ImportError):
            import bubseek.oceanbase  # noqa: F401

    refresh_interval_seconds = 60
    theme_css = """
<style>
:root {
  --sk-bg: #f8fafc;
  --sk-surface: #ffffff;
  --sk-border: #e2e8f0;
  --sk-text: #0f172a;
  --sk-muted: #64748b;
  --sk-accent: #0d9488;
  --sk-accent2: #7c3aed;
}
.sk-wrap {
  font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
  color: var(--sk-text);
  background: var(--sk-bg);
  padding: 1.1rem 1.35rem;
  border-radius: 14px;
  border: 1px solid var(--sk-border);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.sk-h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.03em; margin: 0 0 0.5rem 0; }
.sk-meta { color: var(--sk-muted); font-size: 0.8125rem; margin: 0 0 0.75rem 0; }
.sk-table-wrap { overflow-x: auto; margin-top: 0.5rem; border: 1px solid var(--sk-border); border-radius: 10px; background: var(--sk-surface); }
.sk-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.sk-table th, .sk-table td { text-align: left; padding: 0.45rem 0.65rem; border-bottom: 1px solid var(--sk-border); vertical-align: top; }
.sk-table th { background: #f1f5f9; color: var(--sk-accent2); font-weight: 650; }
.sk-table tr:last-child td { border-bottom: none; }
.sk-err { color: #b91c1c; font-size: 0.875rem; margin: 0 0 0.5rem 0; }
</style>
"""
    return (
        UTC,
        create_engine,
        datetime,
        MetaData,
        Table,
        case,
        inspect,
        mo,
        pickle,
        refresh_interval_seconds,
        select,
        tapestore_url,
        text,
        theme_css,
    )


@app.cell
def _(mo, refresh_interval_seconds):
    refresh = mo.ui.refresh(
        default_interval=refresh_interval_seconds,
        label="Refresh",
    )
    return (refresh,)


@app.cell
def _(mo):
    job_id_filter = mo.ui.text(
        value="",
        label="Search id",
        placeholder="job id…",
    )
    return (job_id_filter,)


@app.cell
def _(  # noqa: C901
    UTC,
    MetaData,
    Table,
    case,
    create_engine,
    datetime,
    inspect,
    mo,
    pickle,
    refresh,
    select,
    tapestore_url,
    text,
    theme_css,
    job_id_filter,
):
    _ = refresh.value
    _ = job_id_filter.value
    import html as html_module

    def _find_jobs_table(insp) -> str | None:
        names = list(insp.get_table_names())
        low = {n.lower(): n for n in names}
        if "apscheduler_jobs" in low:
            return low["apscheduler_jobs"]
        return None

    def _has_jobs_table(engine) -> tuple[bool, str | None]:
        try:
            insp = inspect(engine)
            t = _find_jobs_table(insp)
            if not t:
                return False, None
            ok = insp.has_table(t)
            return bool(ok), t
        except Exception:
            return False, None

    def _fmt_next_run_cell(v) -> str:
        if v is None:
            return "—"
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=UTC)
            return v.astimezone(UTC).isoformat(timespec="seconds")
        if isinstance(v, (int, float)):
            try:
                return datetime.fromtimestamp(float(v), tz=UTC).isoformat(timespec="seconds")
            except (OSError, OverflowError, ValueError):
                return str(v)
        return str(v)

    def _blob_to_bytes(raw) -> bytes:
        if raw is None:
            return b""
        if isinstance(raw, memoryview):
            return raw.tobytes()
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, bytearray):
            return bytes(raw)
        return bytes(raw)

    def _summarize_job_state(raw, pickle_mod) -> dict:
        b = _blob_to_bytes(raw)
        if not b:
            return {"message": "", "fallback": ""}
        try:
            obj = pickle_mod.loads(b)
        except Exception as exc:
            return {"message": "", "fallback": str(exc)[:160]}
        if isinstance(obj, dict) and obj.get("version") == 1:
            kw = obj.get("kwargs") or {}
            msg = kw.get("message") if isinstance(kw, dict) else None
            return {
                "message": str(msg)[:400] if msg is not None else "",
                "fallback": str(kw)[:200] if kw else "",
            }
        kw = getattr(obj, "kwargs", None)
        msg = kw.get("message") if isinstance(kw, dict) else None
        return {
            "message": str(msg)[:400] if msg is not None else "",
            "fallback": str(kw)[:200] if kw is not None else "",
        }

    error_msg = ""
    table_name: str | None = None
    probe_ok = False
    rows_out: list[dict] = []

    try:
        engine = create_engine(tapestore_url, pool_pre_ping=True)
        with engine.connect() as conn:
            probe_ok = conn.execute(text("SELECT 1")).scalar() == 1
        has_t, table_name = _has_jobs_table(engine)
        if has_t and table_name:
            # Table name must still exist in inspector (avoid dynamic SQL on untrusted strings).
            insp2 = inspect(engine)
            if table_name not in set(insp2.get_table_names()):
                error_msg = f"table {table_name!r} not in schema"
            else:
                md = MetaData()
                tbl = Table(table_name, md, autoload_with=engine)
                nulls_last = case((tbl.c.next_run_time.is_(None), 1), else_=0)
                stmt = select(tbl.c.id, tbl.c.next_run_time, tbl.c.job_state).order_by(
                    nulls_last.asc(), tbl.c.next_run_time.asc()
                )
                with engine.connect() as conn:
                    result = conn.execute(stmt)
                    filt = (job_id_filter.value or "").strip().lower()
                    for row in result:
                        m = row._mapping
                        jid = m.get("id")
                        jid_str = str(jid) if jid is not None else ""
                        if filt and filt not in jid_str.lower():
                            continue
                        nrt = m.get("next_run_time")
                        js = m.get("job_state")
                        summary = _summarize_job_state(js, pickle)
                        msg = (summary.get("message") or "").strip()
                        fb = (summary.get("fallback") or "").strip()
                        note = msg or fb or "—"
                        rows_out.append({
                            "id": jid_str,
                            "run_at": _fmt_next_run_cell(nrt),
                            "note": note,
                        })
    except Exception as exc:
        error_msg = str(exc)

    displayed = len(rows_out)
    filt_active = bool((job_id_filter.value or "").strip())
    he = html_module.escape

    if error_msg:
        meta_line = ""
        err_html = f"<p class='sk-err'>{he(error_msg)}</p>"
    elif not probe_ok:
        meta_line = ""
        err_html = "<p class='sk-err'>Cannot connect to database.</p>"
    elif not table_name:
        meta_line = ""
        err_html = "<p class='sk-err'>No schedule table in this database.</p>"
    else:
        err_html = ""
        if displayed:
            meta_line = f"{displayed} scheduled task{'s' if displayed != 1 else ''}"
        elif filt_active:
            meta_line = "No matching tasks"
        else:
            meta_line = "No scheduled tasks"

    meta_html = f'<p class="sk-meta">{he(meta_line)}</p>' if meta_line else ""

    thead = "<thead><tr><th>Id</th><th>Run at</th><th>Message</th></tr></thead>"
    body_rows = []
    for r in rows_out:
        body_rows.append(
            "<tr>"
            f"<td><code>{he(str(r['id']))}</code></td>"
            f"<td>{he(str(r['run_at']))}</td>"
            f"<td style='white-space:pre-wrap;word-break:break-word;'>{he(str(r['note'])[:500])}</td>"
            "</tr>"
        )
    tbody = "<tbody>" + "".join(body_rows) + "</tbody>" if body_rows else "<tbody><tr><td colspan='3'>—</td></tbody>"

    page_html = f"""
{theme_css}
<div class="sk-wrap">
  <h1 class="sk-h1">Scheduled tasks</h1>
  {meta_html}
  {err_html}
  <div class="sk-table-wrap">
    <table class="sk-table">{thead}{tbody}</table>
  </div>
</div>
"""
    page = mo.Html(page_html)
    return (page,)


@app.cell
def _(job_id_filter, mo, page, refresh):
    mo.vstack([refresh, job_id_filter, page], gap=1)
    return ()
