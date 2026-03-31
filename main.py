import uuid
import logging
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, engine, Base
from models import Tenant, Document
from auth import get_current_tenant
from chunker import extract_text, chunk_text
from embedder import store_chunks, search_chunks, delete_document_chunks
from generator import generate_answer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Multi-tenant RAG API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/tenants/register")
async def register_tenant(name: str, db: Session = Depends(get_db)):
    api_key = f"rag-{uuid.uuid4().hex}"
    tenant  = Tenant(name=name, api_key=api_key)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    logger.info(f"Tenant registered: {tenant.name}")
    return {"tenant_id": str(tenant.id), "api_key": api_key}


@app.post("/documents/upload")
async def upload_document(
    file:   UploadFile = File(...),
    tenant: Tenant     = Depends(get_current_tenant),
    db:     Session    = Depends(get_db),
):
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload PDF or plain text."
        )

    file_bytes = await file.read()

    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="File exceeds 10MB limit."
        )

    text        = extract_text(file_bytes, file.content_type)
    chunks      = chunk_text(text)
    document_id = uuid.uuid4()

    try:
        chunk_count = store_chunks(
            chunks, tenant.id, str(document_id), file.filename
        )
        document = Document(
            id=document_id,
            filename=file.filename,
            tenant_id=tenant.id,
            chunk_count=chunk_count,
        )
        db.add(document)
        db.commit()

        logger.info(
            f"Document uploaded | "
            f"tenant={tenant.name} | "
            f"file={file.filename} | "
            f"chunks={chunk_count}"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {
        "document_id": str(document_id),
        "filename":    file.filename,
        "chunk_count": chunk_count,
    }


@app.post("/query")
async def query_documents(
    question: str    = Form(...),
    tenant:   Tenant = Depends(get_current_tenant),
):
    if not question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")

    chunks   = search_chunks(question, tenant.id)
    response = generate_answer(question, chunks)

    logger.info(
        f"Query answered | "
        f"tenant={tenant.name} | "
        f"sources={len(response['sources'])}"
    )

    return response



# ── List documents ────────────────────────────────────
@app.get("/documents")
async def list_documents(
    tenant: Tenant  = Depends(get_current_tenant),
    db:     Session = Depends(get_db),
):
    documents = (
        db.query(Document)
        .filter(Document.tenant_id == tenant.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return [
        {
            "document_id": str(doc.id),
            "filename":    doc.filename,
            "chunk_count": doc.chunk_count,
            "uploaded_at": doc.uploaded_at,
        }
        for doc in documents
    ]


# ── Delete document ───────────────────────────────────
@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    tenant:      Tenant  = Depends(get_current_tenant),
    db:          Session = Depends(get_db),
):
    # find document — must belong to this tenant
    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.tenant_id == tenant.id      # security — tenant can only delete their own
        )
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        # delete from ChromaDB first
        delete_document_chunks(document_id)

        # then delete from Postgres
        db.delete(document)
        db.commit()

        logger.info(
            f"Document deleted | "
            f"tenant={tenant.name} | "
            f"file={document.filename}"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")

    return {"deleted": document_id, "filename": document.filename}