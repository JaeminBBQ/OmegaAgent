# Database Migrations

SQL migrations for Supabase database schema.

## Running Migrations

Execute these SQL files in your Supabase SQL Editor in order:

1. `001_papers_schema.sql` - Papers RAG system (pgvector, tables, indexes, functions)

## Supabase Setup

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Copy and paste the migration SQL
4. Click **Run**

## Schema Overview

### Tables

**papers**
- Stores paper metadata (title, authors, year, DOI, file path)
- Content hash for duplicate detection
- Visibility toggle for dashboard

**paper_chunks**
- Chunked paper text with 1024-dim embeddings (bge-large-en-v1.5)
- Links to parent paper
- Page numbers for citations

**research_notes**
- Obsidian research notes with embeddings
- Synced from `vault/notes/research/`

### Functions

**search_paper_chunks(query_embedding, threshold, limit)**
- Semantic search over paper chunks
- Returns paper metadata + matching chunks + similarity scores

**search_research_notes(query_embedding, threshold, limit)**
- Semantic search over research notes
- Returns note content + similarity scores

**find_duplicate_papers(title, threshold)**
- Fuzzy title matching for duplicate detection
- Uses trigram similarity

## Vector Search

Uses pgvector with IVFFlat indexes for fast approximate nearest neighbor search.
- Cosine similarity metric
- 1024 dimensions (bge-large-en-v1.5)
