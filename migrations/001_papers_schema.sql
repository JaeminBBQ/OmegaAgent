-- Enable pgvector extension for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Papers table: metadata for uploaded academic papers
CREATE TABLE papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    authors TEXT[] DEFAULT '{}',
    year INTEGER,
    doi TEXT,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    page_count INTEGER,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    visible_on_dashboard BOOLEAN DEFAULT TRUE,
    CONSTRAINT valid_year CHECK (year IS NULL OR (year >= 1900 AND year <= 2100))
);

-- Paper chunks: chunked text with embeddings for RAG retrieval
CREATE TABLE paper_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    page_number INTEGER,
    content TEXT NOT NULL,
    embedding VECTOR(1024),  -- bge-large-en-v1.5 dimensions
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(paper_id, chunk_index)
);

-- Research notes: embeddings for Obsidian research notes
CREATE TABLE research_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast retrieval
CREATE INDEX idx_papers_title ON papers USING GIN (to_tsvector('english', title));
CREATE INDEX idx_papers_authors ON papers USING GIN (authors);
CREATE INDEX idx_papers_uploaded ON papers(uploaded_at DESC);
CREATE INDEX idx_papers_visible ON papers(visible_on_dashboard) WHERE visible_on_dashboard = true;

-- Vector similarity search indexes (IVFFlat for speed)
CREATE INDEX idx_paper_chunks_embedding ON paper_chunks 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX idx_research_notes_embedding ON research_notes 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- Helper function: search papers by semantic similarity
CREATE OR REPLACE FUNCTION search_paper_chunks(
    query_embedding VECTOR(1024),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    paper_id UUID,
    paper_title TEXT,
    paper_authors TEXT[],
    chunk_content TEXT,
    page_number INTEGER,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.title,
        p.authors,
        pc.content,
        pc.page_number,
        1 - (pc.embedding <=> query_embedding) AS similarity
    FROM paper_chunks pc
    JOIN papers p ON pc.paper_id = p.id
    WHERE 1 - (pc.embedding <=> query_embedding) > match_threshold
    ORDER BY pc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Helper function: search research notes by semantic similarity
CREATE OR REPLACE FUNCTION search_research_notes(
    query_embedding VECTOR(1024),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    note_id UUID,
    note_title TEXT,
    note_content TEXT,
    file_path TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        rn.id,
        rn.title,
        rn.content,
        rn.file_path,
        1 - (rn.embedding <=> query_embedding) AS similarity
    FROM research_notes rn
    WHERE 1 - (rn.embedding <=> query_embedding) > match_threshold
    ORDER BY rn.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Helper function: find duplicate papers by title similarity
CREATE OR REPLACE FUNCTION find_duplicate_papers(
    paper_title TEXT,
    similarity_threshold FLOAT DEFAULT 0.9
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    authors TEXT[],
    similarity DOUBLE PRECISION
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.title,
        p.authors,
        CAST(similarity(p.title, paper_title) AS DOUBLE PRECISION) AS sim
    FROM papers p
    WHERE similarity(p.title, paper_title) > similarity_threshold
    ORDER BY sim DESC;
END;
$$;

-- Enable trigram similarity for title matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_papers_title_trgm ON papers USING GIN (title gin_trgm_ops);
