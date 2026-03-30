#!/usr/bin/env python3
"""Query `apscheduler_jobs` in the same DB the gateway uses.

Use when Marimo schedule kanban shows no rows but the assistant reported a job id.

Examples::

    uv run python scripts/query_apscheduler_jobs.py
    uv run python scripts/query_apscheduler_jobs.py --job-id 6718144d
    uv run python scripts/query_apscheduler_jobs.py --workspace /path/to/bubseek
    BUB_TAPESTORE_SQLALCHEMY_URL='mysql+oceanbase://...' uv run python scripts/query_apscheduler_jobs.py
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="List APScheduler persisted jobs (debug).")
    parser.add_argument(
        "--workspace",
        type=Path,
        help="bubseek project root containing .env (default: cwd, with parent walk for .env)",
    )
    parser.add_argument("--job-id", dest="job_id", help="only print rows whose id contains this substring")
    parser.add_argument("--url", help="override SQLAlchemy URL")
    args = parser.parse_args()

    if args.url:
        url = args.url.strip()
        label = "cli --url"
    elif (os.environ.get("BUB_TAPESTORE_SQLALCHEMY_URL") or "").strip():
        url = os.environ["BUB_TAPESTORE_SQLALCHEMY_URL"].strip()
        label = "env BUB_TAPESTORE_SQLALCHEMY_URL"
    else:
        from bubseek.config import resolve_tapestore_url

        ws = args.workspace.resolve() if args.workspace else None
        if ws is not None:
            url = resolve_tapestore_url(workspace=ws)
            label = f"resolve_tapestore_url(workspace={ws})"
        else:
            url = resolve_tapestore_url()
            label = "resolve_tapestore_url() from cwd / .env walk"

    if not url:
        print("Could not resolve tapestore URL.", file=sys.stderr)
        return 1

    print(f"Source: {label}")
    print(f"URL (first 120 chars): {url[:120]}{'...' if len(url) > 120 else ''}")

    with contextlib.suppress(ImportError):
        import bubseek.oceanbase  # noqa: F401

    from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            one = conn.execute(text("SELECT 1")).scalar()
            if one != 1:
                print("SELECT 1 failed.", file=sys.stderr)
                return 1
    except Exception as exc:
        print(f"Connection error: {exc}", file=sys.stderr)
        return 1

    insp = inspect(engine)
    names = {n.lower(): n for n in insp.get_table_names()}
    tname = names.get("apscheduler_jobs")
    if not tname:
        print("No table apscheduler_jobs in this database.", file=sys.stderr)
        return 1

    md = MetaData()
    tbl = Table(tname, md, autoload_with=engine)
    stmt = select(tbl.c.id, tbl.c.next_run_time).order_by(tbl.c.next_run_time.asc())
    sub = (args.job_id or "").strip().lower()

    with engine.connect() as conn:
        rows = list(conn.execute(stmt))

    if sub:
        rows = [r for r in rows if sub in str(r[0]).lower()]

    print(f"Rows{' (filtered)' if sub else ''}: {len(rows)}")
    for rid, nrt in rows:
        print(f"  id={rid!r}  next_run_time={nrt!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
