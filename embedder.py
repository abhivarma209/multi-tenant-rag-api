import os
import uuid
from openai import OpenAI
from database import get_chroma_client, get_collection

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
EMBEDDING_MODEL = "text-embedding-3-small"


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts
    )
    return [item.embedding for item in response.data]


def store_chunks(
    chunks:       list[str],
    tenant_id:    str,
    document_id:  str,
    filename:     str,
) -> int:
    if not chunks:
        return 0

    # batch embed all chunks in one API call
    embeddings = embed_texts(chunks)

    # build parallel lists — ChromaDB requires these
    ids       = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "tenant_id":   str(tenant_id),
            "document_id": str(document_id),
            "filename":    filename,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    chroma  = get_chroma_client()
    collection = get_collection(chroma)

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,        # store original text alongside vector
        metadatas=metadatas,
    )

    return len(chunks)


def search_chunks(
    query:     str,
    tenant_id: str,
    n_results: int = 5,
) -> list[dict]:

    # embed the question
    query_embedding = embed_texts([query])[0]

    chroma     = get_chroma_client()
    collection = get_collection(chroma)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"tenant_id": str(tenant_id)},   # tenant isolation enforced here
        include=["documents", "metadatas", "distances"],
    )

    # reshape into clean list of dicts
    chunks = []
    for i in range(len(results["ids"][0])):
        chunks.append({
            "text":      results["documents"][0][i],
            "filename":  results["metadatas"][0][i]["filename"],
            "chunk_index": results["metadatas"][0][i]["chunk_index"],
            "distance":  results["distances"][0][i],
        })

    return chunks