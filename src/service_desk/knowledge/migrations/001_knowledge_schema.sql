CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id text PRIMARY KEY,
    checksum char(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    corpus_version text NOT NULL,
    chunk_id text NOT NULL,
    chunking_version text NOT NULL,
    document_id text NOT NULL,
    document_title text NOT NULL,
    domain text NOT NULL CHECK (domain IN ('billing', 'support', 'technical')),
    product text NOT NULL,
    heading_path jsonb NOT NULL,
    included_heading_paths jsonb NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index > 0),
    source_path text NOT NULL,
    content text NOT NULL,
    word_count integer NOT NULL CHECK (word_count > 0),
    content_sha256 char(64) NOT NULL,
    source_commit char(40) NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    PRIMARY KEY (corpus_version, chunk_id)
);

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    corpus_version text NOT NULL,
    chunk_id text NOT NULL,
    embedding_model text NOT NULL,
    embedding_dimensions smallint NOT NULL CHECK (embedding_dimensions = 1536),
    embedding_content_sha256 char(64) NOT NULL,
    embedding vector(1536) NOT NULL,
    embedded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (corpus_version, chunk_id, embedding_model),
    FOREIGN KEY (corpus_version, chunk_id)
        REFERENCES knowledge_chunks (corpus_version, chunk_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS knowledge_chunks_active_corpus_domain_idx
    ON knowledge_chunks (corpus_version, domain)
    WHERE is_active;
