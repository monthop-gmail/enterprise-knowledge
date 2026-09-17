"""PostgreSQL + pgvector access (§8, §9).

The one invariant this module owns: `hnsw.ef_search` and the vector query must
share a transaction. §9 forbids setting a session parameter and handing the
connection back to the pool with it still applied -- `SET LOCAL` inside an
explicit transaction is the only shape allowed here, so the setting dies at
COMMIT and the next borrower of that connection is unaffected.

`psycopg` is imported lazily so the contract layer stays importable without a
database driver installed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Protocol

from .config import Settings
from .errors import StorageError

if TYPE_CHECKING:  # pragma: no cover
    from psycopg import Connection

__all__ = ["Storage", "PostgresStorage"]


def _import_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        raise StorageError(
            "psycopg is not installed: pip install -e '.[dev]' or "
            "pip install 'psycopg[binary,pool]'"
        ) from exc
    return psycopg


class Storage(Protocol):
    """Connection management + schema lifecycle."""

    @contextmanager
    def retrieval_transaction(self, ef_search: int) -> Iterator[Connection]:
        """Yield a connection inside a transaction with `SET LOCAL hnsw.ef_search`."""

    def apply_schema(self, schema_sql: str) -> None: ...

    def close(self) -> None: ...


class PostgresStorage:
    """`psycopg` v3 `ConnectionPool` implementation.

    The pool is created on first use rather than in `__init__`, so constructing a
    `PostgresStorage` never opens a socket. Tests and the CLI can build one, read
    its settings, and decide not to touch the database at all.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pool: Any | None = None

    # Fail fast when the database is unreachable: a hung import-time connect is
    # far harder to diagnose than a refused one.
    _OPEN_TIMEOUT_SECONDS = 10.0

    def _ensure_pool(self) -> Any:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise StorageError(
                "psycopg is not installed: pip install -e '.[dev]' or "
                "pip install 'psycopg[binary,pool]'"
            ) from exc
        if self._pool is None:
            pool = ConnectionPool(
                conninfo=self.settings.database_url,
                min_size=self.settings.pool_min_size,
                max_size=self.settings.pool_max_size,
                open=False,
            )
            try:
                pool.open(wait=True, timeout=self._OPEN_TIMEOUT_SECONDS)
            except Exception as exc:
                pool.close()
                raise StorageError(
                    f"could not open a connection pool to the database: {exc}"
                ) from exc
            self._pool = pool
        return self._pool

    @contextmanager
    def retrieval_transaction(self, ef_search: int) -> Iterator[Connection]:
        """The only sanctioned way to run a vector query (§9).

            BEGIN
              SET LOCAL hnsw.ef_search = <n>
              <vector query>
            COMMIT

        Do not add a non-LOCAL `SET` anywhere in this class.
        """
        pool = self._ensure_pool()
        with pool.connection() as conn:
            self._assert_no_open_transaction(conn)
            with conn.transaction():
                with conn.cursor() as cur:
                    # SET LOCAL will not accept a bind parameter, so the value is
                    # rendered -- hence the int() guard rather than a driver bind.
                    cur.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
                yield conn

    @staticmethod
    def _assert_no_open_transaction(conn: Connection) -> None:
        """Refuse to run if a transaction is already open on this connection.

        Verified against PostgreSQL 16 + pgvector 0.8: `psycopg` opens an implicit
        transaction on the first statement, and `conn.transaction()` then issues a
        SAVEPOINT rather than a BEGIN. Releasing a savepoint does **not** unwind
        `SET LOCAL` -- the setting survives until the *outer* transaction ends, so
        every later query on that connection silently runs with someone else's
        `ef_search`. §9 calls that out as the exact failure mode to avoid, and it
        is invisible in testing because results stay plausible, just differently
        recalled.

        Cheap to check, so it is checked every time rather than trusted.
        """
        from psycopg.pq import TransactionStatus

        status = conn.info.transaction_status
        if status != TransactionStatus.IDLE:
            raise StorageError(
                "retrieval_transaction() requires a connection with no open transaction "
                f"(status={status!r}); otherwise SET LOCAL hnsw.ef_search degrades to a "
                "savepoint-scoped setting and leaks into subsequent queries (§9)"
            )

    def apply_schema(self, schema_sql: str) -> None:
        """Run a schema script against the database. Idempotent.

        Uses a dedicated autocommit connection rather than one from the pool, for
        two reasons. The script carries its own `BEGIN`/`COMMIT`, which would
        collide with the transaction psycopg opens implicitly on a pooled
        connection; and applying DDL is an administrative one-off, not the
        workload the pool is sized for, so it has no business consuming a slot or
        leaving connection state behind.
        """
        psycopg = _import_psycopg()
        try:
            with (
                psycopg.connect(self.settings.database_url, autocommit=True) as conn,
                conn.cursor() as cur,
            ):
                cur.execute(schema_sql)
        except psycopg.Error as exc:
            raise StorageError(f"applying the schema failed: {exc}") from exc

    def close(self) -> None:
        """Release the pool. Safe to call more than once, and on an unused storage."""
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def __enter__(self) -> PostgresStorage:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
