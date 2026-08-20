"""Live PostgreSQL + pgvector checks (§18 integration mode, §23 DoD "Core").

Skipped unless a database is reachable:

    docker compose up -d && make schema && pytest -m integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def conn(database_url: str | None):
    psycopg = pytest.importorskip("psycopg")
    if not database_url:
        pytest.skip("EK_DATABASE_URL not set")
    try:
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            yield connection
    except psycopg.OperationalError as exc:  # pragma: no cover
        pytest.skip(f"database unreachable: {exc}")


def test_extensions_present(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension")
        names = {row[0] for row in cur.fetchall()}
    assert {"vector", "pgcrypto"} <= names


def test_required_indexes_exist(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'langchain_hybrid_docs'"
        )
        names = {row[0] for row in cur.fetchall()}
    assert "langchain_hybrid_docs_embedding_hnsw" in names
    assert "langchain_hybrid_docs_tsv_gin" in names
    assert "langchain_hybrid_docs_metadata_gin" in names


def test_tenant_id_is_not_nullable(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'langchain_hybrid_docs' AND column_name = 'tenant_id'"
        )
        (is_nullable,) = cur.fetchone()
    assert is_nullable == "NO", "the tenant boundary is a NOT NULL column (§4.3)"


def test_set_local_ef_search_dies_at_commit(conn) -> None:
    """§9: in a real transaction, SET LOCAL must not survive COMMIT."""
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SET LOCAL hnsw.ef_search = 123")
        cur.execute("SHOW hnsw.ef_search")
        assert cur.fetchone()[0] == "123"
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SHOW hnsw.ef_search")
        assert cur.fetchone()[0] != "123", "ef_search leaked past COMMIT"


def test_set_local_leaks_when_nested_in_an_open_transaction(conn) -> None:
    """The failure mode `PostgresStorage._assert_no_open_transaction` guards against.

    `psycopg` opens an implicit transaction on the first statement, which turns a
    following `conn.transaction()` into a SAVEPOINT. Releasing a savepoint does not
    unwind SET LOCAL, so the setting outlives the block. This test pins that
    behaviour so the guard is never removed as "unnecessary".
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchall()
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SET LOCAL hnsw.ef_search = 123")
    with conn.cursor() as cur:
        cur.execute("SHOW hnsw.ef_search")
        assert cur.fetchone()[0] == "123", "expected the documented savepoint leak"
    conn.commit()


def test_storage_refuses_a_connection_with_an_open_transaction(conn) -> None:
    from enterprise_knowledge.errors import StorageError
    from enterprise_knowledge.storage import PostgresStorage

    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchall()
    with pytest.raises(StorageError, match="open transaction"):
        PostgresStorage._assert_no_open_transaction(conn)
    conn.commit()
