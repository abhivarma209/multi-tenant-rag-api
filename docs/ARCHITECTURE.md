# Architecture — Multi-Tenant RAG API

## System Overview

```
Client Request (with X-API-Key header)
            |
            v
      FastAPI (main.py)
            |
      auth.py — validate API key → get tenant from Postgres
            |
   ┌────────┴────────┐
   |                 |
Upload Flow      Query Flow
   |                 |
chunker.py      embedder.py
extract text    embed question
chunk text      search ChromaDB
   |            filter by tenant_id
embedder.py          |
embed chunks    generator.py
store ChromaDB  build context
store Postgres  call GPT-4o-mini
   |            return answer + sources
return summary
```

## File Responsibilities

| File | Responsibility |
|------|---------------|
| `main.py` | FastAPI app, endpoints, middleware, startup |
| `models.py` | SQLAlchemy ORM — Tenant, Document tables |
| `auth.py` | API key validation, tenant extraction |
| `chunker.py` | PDF/text extraction, recursive text splitting |
| `embedder.py` | OpenAI embeddings, ChromaDB store and search |
| `generator.py` | Context building, LLM answer generation |
| `database.py` | Postgres + ChromaDB connection management |

## Key Design Decisions

### 1. Tenant isolation via metadata filtering
All tenants share one ChromaDB collection. Isolation is enforced by
attaching `tenant_id` to every chunk and filtering every search:

```python
results = collection.query(
    query_embeddings=[query_embedding],
    where={"tenant_id": str(tenant_id)},   # hard filter — no other tenant's data
)
```

Alternative was one collection per tenant. Rejected because it does not
scale to many tenants and adds collection management overhead.

### 2. Two databases, two jobs
- **ChromaDB** — stores vectors and chunk text. Optimised for similarity search.
- **PostgreSQL** — stores tenant records, API keys, document metadata.
  Optimised for relational queries and transactional integrity.

Trying to use one database for both would mean either:
- Storing vectors in Postgres (slow similarity search without pgvector)
- Storing relational data in ChromaDB (no foreign keys, no transactions)

### 3. Batch embedding over per-chunk embedding
All chunks from a document are embedded in a single OpenAI API call.
Per-chunk calls would multiply network latency by the number of chunks
and risk hitting rate limits on large documents.

### 4. RecursiveCharacterTextSplitter with overlap
- chunk_size=3200 characters (~800 tokens)
- chunk_overlap=600 characters (~150 tokens)

Overlap prevents semantic loss at chunk boundaries. Without overlap,
a sentence split across two chunks loses context at the cut point.
RecursiveCharacterTextSplitter splits on paragraph → sentence → word
boundaries before resorting to character splits.

### 5. Grounding instruction prevents hallucination
System prompt requires the model to answer ONLY from provided context:

```
"If the answer is not in the context, say exactly:
'I couldn't find this information in your documents.'"
```

A confident wrong answer in a RAG system is worse than no answer.
Users act on answers — incorrect information causes real harm.

### 6. Early return on empty retrieval
If ChromaDB returns no chunks, generator.py returns immediately
without calling the LLM. Saves API cost and gives a cleaner response.

### 7. db.rollback() on upload failure
If ChromaDB succeeds but Postgres fails, we have orphaned vectors
with no document record. rollback() ensures partial failures leave
the system in a consistent state.

### 8. Named Docker volumes for data persistence
```yaml
volumes:
  postgres_data:
  chroma_data:
```
Data survives container restarts. `docker compose down` is safe.
`docker compose down -v` destroys volumes — never run in production.

## Chunking Strategy

```
Document (50 pages)
    ↓
RecursiveCharacterTextSplitter
    ↓
[chunk_0][chunk_1][chunk_2]...[chunk_n]
    |         |
    |    600 char overlap
    |←————————|
```

Each chunk gets embedded independently. The overlap ensures no
sentence is ever fully split across two chunks.

## Query Flow — Step by Step

```
1. Tenant sends question + X-API-Key header
2. auth.py validates key → extracts tenant object
3. question → OpenAI embeddings API → query vector
4. ChromaDB cosine similarity search, filtered by tenant_id
5. Top 5 most similar chunks retrieved
6. Chunks formatted with source labels into context string
7. Context + question → GPT-4o-mini (temperature=0)
8. Answer + source list returned to tenant
```

## Token Economics

- Embedding model: text-embedding-3-small
  ~$0.00002 per 1K tokens — 100 chunks costs less than $0.01
- Generation model: gpt-4o-mini
  ~$0.00015 per 1K tokens — 5 retrieved chunks + answer costs ~$0.001
- Cost per query at this scale: under $0.002
