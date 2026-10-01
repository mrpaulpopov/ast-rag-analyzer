CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS code_knowledge_base (
    id SERIAL PRIMARY KEY,

    file_path TEXT NOT NULL,
    func_name TEXT NOT NULL,

    raw_code TEXT NOT NULL,

    docstring TEXT NOT NULL,

    embedding vector(768)
);

CREATE INDEX ON code_knowledge_base USING hnsw (embedding vector_cosine_ops); -- HNSW (Hierarchical Navigable Small World)
