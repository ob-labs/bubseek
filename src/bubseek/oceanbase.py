"""Register pyobvector SQLAlchemy dialect for OceanBase/seekdb compatibility."""

from __future__ import annotations

import pymysql
import pyobvector  # noqa: F401
from bub import hookimpl
from pyobvector.schema.dialect import OceanBaseDialect as _OceanBaseDialect
from sqlalchemy.dialects import registry


def _is_savepoint_not_exist(exc: BaseException) -> bool:
    """Check if exception is MySQL 1305 (savepoint does not exist)."""
    if isinstance(exc, pymysql.err.OperationalError) and exc.args and exc.args[0] == 1305:
        return True
    orig = getattr(exc, "orig", None)
    if orig is not None and orig is not exc:
        return _is_savepoint_not_exist(orig)
    return False


class OceanBaseDialect(_OceanBaseDialect):
    """OceanBase dialect that tolerates missing savepoints.

    OceanBase/seekdb may implicitly release savepoints on errors (e.g. deadlock,
    failed DML). When SQLAlchemy later tries RELEASE SAVEPOINT or ROLLBACK TO
    SAVEPOINT, it gets (1305, 'savepoint does not exist'). We catch and ignore
    that to avoid masking the original error.
    """

    # SQLAlchemy only reads this on the concrete dialect class (__dict__), not via MRO.
    supports_statement_cache = True

    def do_release_savepoint(self, connection, name: str) -> None:
        try:
            super().do_release_savepoint(connection, name)
        except Exception as e:
            if not _is_savepoint_not_exist(e):
                raise

    def do_rollback_to_savepoint(self, connection, name: str) -> None:
        try:
            super().do_rollback_to_savepoint(connection, name)
        except Exception as e:
            if not _is_savepoint_not_exist(e):
                raise


registry.register("mysql.oceanbase", "bubseek.oceanbase", "OceanBaseDialect")


def _patch_tape_store_validate_schema() -> None:
    """Tolerate duplicate index (MySQL 1061) in bub_tapestore_sqlalchemy.

    seekdb/OceanBase introspection may not match SQLAlchemy's checkfirst, so
    CREATE INDEX is attempted even when the index already exists on the table.
    """
    try:
        from bub_tapestore_sqlalchemy import store as _store
    except ImportError:
        return
    _Store = _store.SQLAlchemyTapeStore
    _orig = _Store._validate_schema

    def _validate_schema_tolerant(self: _Store) -> None:
        try:
            _orig(self)
        except Exception as e:
            _orig_e = getattr(e, "orig", e)
            if getattr(_orig_e, "args", (None,))[0] == 1061:
                return
            if "Duplicate key name" in str(e):
                return
            raise

    _store.SQLAlchemyTapeStore._validate_schema = _validate_schema_tolerant  # type: ignore[method-assign]


_patch_tape_store_validate_schema()


def register(framework: object) -> object:
    """Bub plugin entry point. Registers dialect only."""
    return _OceanBaseDialectPlugin()


class _OceanBaseDialectPlugin:
    """Minimal plugin to satisfy Bub loader. Dialect already registered at import."""

    @hookimpl
    def provide_tape_store(self) -> None:
        """Skip; let bub_tapestore_sqlalchemy provide the store."""
        return None
