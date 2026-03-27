# Multi-Tenant RAG API

A production-grade Retrieval-Augmented Generation (RAG) API where multiple tenants can upload private documents and query them using natural language. Complete tenant isolation — Company A never sees Company B's data.

## Live Demo
**API:** coming soon  
**Docs:** coming soon

## What it does

```
Tenant registers → gets API key
Tenant uploads PDF/text → chunked, embedded, stored in ChromaDB
Tenant asks question → semantic search → GPT-4o-mini answers from their docs only
```

```json
POST /query
{
  "answer": "The total amount due is 30,798.89. [Source 1]",
  "sources": [
    { "filename": "invoice.pdf", "chunk_index": 0 }
  ]
}
```

## Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/tenants/register` | None | Register tenant, get API key |
| POST | `/documents/upload` | X-API-Key | Upload PDF or text document |
| POST | `/query` | X-API-Key | Ask a question against your documents |
| GET | `/health` | None | Health check |
| GET | `/docs` | None | Swagger UI |

## Tech Stack

- **FastAPI** — async Python API
- **ChromaDB** — vector database for semantic search
- **PostgreSQL** — tenant registry and document metadata
- **OpenAI** — embeddings (text-embedding-3-small) + GPT-4o-mini
- **LangChain** — document chunking with RecursiveCharacterTextSplitter
- **SQLAlchemy** — ORM for PostgreSQL
- **Docker Compose** — runs API + Postgres + ChromaDB together

## Run Locally

```bash
git clone https://github.com/abhivarma209/rag-api
cd rag-api
cp .env.example .env        # add your OPENAI_API_KEY
docker compose up --build
# API live at http://localhost:8000/docs
```

## Quick Test

```bash
# 1. Register a tenant
curl -X POST "http://localhost:8000/tenants/register?name=MyCompany"
# → {"tenant_id": "...", "api_key": "rag-xxxxx"}

# 2. Upload a document
curl -X POST "http://localhost:8000/documents/upload" \
  -H "X-API-Key: rag-xxxxx" \
  -F "file=@invoice.pdf"

# 3. Ask a question
curl -X POST "http://localhost:8000/query" \
  -H "X-API-Key: rag-xxxxx" \
  -F "question=What is the total amount due?"
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed design decisions.

## Learnings

See [docs/LEARNINGS.md](./docs/LEARNINGS.md) for concepts covered building this project.
