import os
import chromadb
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ── PostgreSQL ────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── ChromaDB ──────────────────────────────────────────
def get_chroma_client():
    return chromadb.HttpClient(
        host=os.getenv("CHROMA_HOST", "localhost"),
        port=int(os.getenv("CHROMA_PORT", "8001"))
    )

def get_collection(client: chromadb.HttpClient):
    return client.get_or_create_collection(
        name="documents",
        metadata={"hnsw:space": "cosine"}   # cosine similarity for semantic search
    )
