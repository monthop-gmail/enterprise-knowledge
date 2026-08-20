-- enterprise-knowledge :: Knowledge Plane storage schema
-- Ref: ref/hybrid-rag-prompt-review.md  §8 (PostgreSQL Design), §4.3 (Tenant Isolation)
--
-- Idempotent: safe to run repeatedly against a clean or existing database.
-- Target: PostgreSQL 16 + pgvector >= 0.7

BEGIN;

-- §8: prefer pgcrypto/gen_random_uuid() over uuid-ossp
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Chunk table
-- ---------------------------------------------------------------------------
-- One row = one retrievable chunk.
--
-- DEVIATION from the literal field list in §8 (id/content/metadata/embedding/
-- tsv_content): tenant_id, document_id, chunk_index and source are promoted to
-- real columns instead of living inside `metadata`. Rationale: §4.3 requires the
-- tenant boundary to be *hard* -- a JSONB key can be forgotten by a caller, a
-- NOT NULL column cannot. document_id/chunk_index/source are required by the
-- provenance contract (§10) on every single result, so they are not optional
-- metadata either. Everything else stays in `metadata` JSONB.
CREATE TABLE IF NOT EXISTS langchain_hybrid_docs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- hard security boundary (§4.3)
    tenant_id    TEXT  NOT NULL,

    -- provenance identity (§10)
    document_id  TEXT  NOT NULL,
    chunk_index  INT   NOT NULL DEFAULT 0,
    source       TEXT,

    content      TEXT  NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- OpenAI text-embedding-3-small = 1536 dims. Keep EMBEDDING_DIM in .env in
    -- sync with this number; changing it requires a re-index, not an ALTER.
    embedding    vector(1536),

    tsv_content  tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT langchain_hybrid_docs_chunk_uniq UNIQUE (tenant_id, document_id, chunk_index)
);

-- ---------------------------------------------------------------------------
-- Indexes (§8)
-- ---------------------------------------------------------------------------
-- Dense: HNSW cosine
CREATE INDEX IF NOT EXISTS langchain_hybrid_docs_embedding_hnsw
    ON langchain_hybrid_docs USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Sparse: full-text
CREATE INDEX IF NOT EXISTS langchain_hybrid_docs_tsv_gin
    ON langchain_hybrid_docs USING gin (tsv_content);

-- Metadata containment (`metadata @> %s::jsonb`)
CREATE INDEX IF NOT EXISTS langchain_hybrid_docs_metadata_gin
    ON langchain_hybrid_docs USING gin (metadata jsonb_path_ops);

-- Tenant pre-filter: every production query is scoped by tenant_id first, so it
-- leads the composite index.
CREATE INDEX IF NOT EXISTS langchain_hybrid_docs_tenant_doc
    ON langchain_hybrid_docs (tenant_id, document_id);

COMMIT;
