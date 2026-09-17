"""`PostgresStorage` against a live PostgreSQL + pgvector (#1).

These exist because the §9 guarantee is a property of the *code path*, not of a
SQL snippet. Until now `SET LOCAL hnsw.ef_search` had only ever been proven by
hand in a scratch script, which proves nothing about what the package does.

Skipped unless a database is reachable:

    docker compose up -d && make schema && pytest -m integration
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enterprise_knowledge.config import Settings
from enterprise_knowledge.errors import StorageError
from enterprise_knowledge.storage import PostgresStorage

pytestmark = pytest.mark.integration

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "schema.sql"


@pytest.fixture
def storage(database_url: str | None):
    pytest.importorskip("psycopg_pool")
    if not database_url:
        pytest.skip("EK_DATABASE_URL not set")
    store = PostgresStorage(Settings(database_url=database_url))
    try:
        with store.retrieval_transaction(40):
            pass
    except StorageError as exc:  # pragma: no cover - environment dependent
        store.close()
        pytest.skip(f"database unreachable: {exc}")
    yield store
    store.close()


def test_applying_the_schema_twice_is_idempotent(storage: PostgresStorage) -> None:
    """`make schema` is the supported path for an existing database, so it must
    be safe to run on one that is already current."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    storage.apply_schema(sql)
    storage.apply_schema(sql)

    with storage.retrieval_transaction(40) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_indexes WHERE tablename = 'langchain_hybrid_docs'")
        assert cur.fetchone()[0] >= 5


def test_schema_applies_to_a_genuinely_empty_database(database_url: str | None) -> None:
    """DoD §23: the schema must work from a clean database, not just an existing one.

    Runs against a throwaway database so the developer's own data is never at
    risk -- a test that proves "works on empty" by emptying what you have is not
    a test anyone will run twice.
    """
    psycopg = pytest.importorskip("psycopg")
    if not database_url:
        pytest.skip("EK_DATABASE_URL not set")

    scratch = "ek_schema_clean_check"
    admin = psycopg.conninfo.conninfo_to_dict(database_url)
    admin["dbname"] = "postgres"
    admin_url = psycopg.conninfo.make_conninfo(**admin)

    try:
        with (
            psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as conn,
            conn.cursor() as cur,
        ):
            cur.execute(f'DROP DATABASE IF EXISTS "{scratch}"')
            cur.execute(f'CREATE DATABASE "{scratch}"')
    except psycopg.Error as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"cannot create a scratch database: {exc}")

    target = psycopg.conninfo.conninfo_to_dict(database_url)
    target["dbname"] = scratch
    store = PostgresStorage(Settings(database_url=psycopg.conninfo.make_conninfo(**target)))
    try:
        store.apply_schema(SCHEMA_SQL.read_text(encoding="utf-8"))
        with store.retrieval_transaction(40) as conn, conn.cursor() as cur:
            cur.execute("SELECT extname FROM pg_extension")
            assert {"vector", "pgcrypto"} <= {row[0] for row in cur.fetchall()}
            cur.execute("SELECT workspace_id FROM langchain_hybrid_docs LIMIT 0")
    finally:
        store.close()
        with psycopg.connect(admin_url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{scratch}"')


def test_ef_search_is_set_inside_the_transaction(storage: PostgresStorage) -> None:
    with storage.retrieval_transaction(123) as conn, conn.cursor() as cur:
        cur.execute("SHOW hnsw.ef_search")
        assert cur.fetchone()[0] == "123"


def test_ef_search_does_not_survive_into_the_next_checkout(storage: PostgresStorage) -> None:
    """The §9 guarantee, exercised through the real pool rather than by hand.

    `min_size` is 1 by default, so the second checkout is very likely the same
    physical connection -- which is exactly the case that must stay clean.
    """
    with storage.retrieval_transaction(123):
        pass
    with storage.retrieval_transaction(40) as conn, conn.cursor() as cur:
        cur.execute("SHOW hnsw.ef_search")
        assert cur.fetchone()[0] != "123"


def test_ef_search_is_bound_as_an_integer(storage: PostgresStorage) -> None:
    """`SET LOCAL` takes no bind parameter, so the value is rendered into SQL.

    `int()` is the only thing standing between that and an injection point, so
    a non-numeric value must fail rather than reach the statement.
    """
    with (
        pytest.raises((ValueError, TypeError)),
        storage.retrieval_transaction("40; DROP TABLE x"),  # type: ignore[arg-type]
    ):
        pass


def test_close_is_safe_to_repeat(storage: PostgresStorage) -> None:
    storage.close()
    storage.close()


def test_unreachable_database_fails_fast_with_a_storage_error() -> None:
    """A refused connection must surface as StorageError, not as a hang or a
    raw driver exception leaking through the abstraction."""
    pytest.importorskip("psycopg_pool")
    store = PostgresStorage(Settings(database_url="postgresql://ek:ek@localhost:1/nope"))
    try:
        with (
            pytest.raises(StorageError, match="could not open a connection pool"),
            store.retrieval_transaction(40),
        ):
            pass
    finally:
        store.close()
