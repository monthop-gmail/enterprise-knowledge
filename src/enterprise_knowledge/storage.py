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


class Storage(Protocol):
    """Connection management + schema lifecycle."""

    @contextmanager
    def retrieval_transaction(self, ef_search: int) -> Iterator[Connection]:
        """Yield a connection inside a transaction with `SET LOCAL hnsw.ef_search`."""

    def apply_schema(self, schema_sql: str) -> None: ...

    def close(self) -> None: ...


class PostgresStorage:
    """Phase 1: `psycopg` v3 `ConnectionPool` implementation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._pool: Any | None = None

    def _ensure_pool(self) -> Any:
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover
            raise StorageError(
                "psycopg is not installed: pip install -e '.[dev]' or "
                "pip install 'psycopg[binary,pool]'"
            ) from exc
        if self._pool is None:
            self._pool = ConnectionPool(
                conninfo=self.settings.database_url,
                min_size=self.settings.pool_min_size,
                max_size=self.settings.pool_max_size,
                open=True,
            )
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
        raise NotImplementedError("Phase 1: execute schema.sql against a clean database")

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None
